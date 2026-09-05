#!/usr/bin/env python3
"""Persistent Discord bridge for herdr agents.

Runs as a herdr [[startup]] long-runner (herdr startup hooks are one-shot
and unsupervised, so this file carries the omp-watch hygiene itself:
machine-wide flock, orphan guard, internal crash-respawn). Responsibilities:

- Provision one Discord text channel per agent under a category, named
  after the agent's project directory (the identity the user thinks in),
  plus a webhook per channel for the notify hook. Reconciled on startup
  and every RECONCILE_SECONDS so agents that appear mid-session get
  channels too.
- Relay allowlisted plain messages from an agent's channel into the agent
  via `herdr agent prompt <pane_id> <text>` (fire-and-forget), with
  agent_blocked / stalled surfaced back into the channel.
- `!status` and `!tail [n]` for superficial inspection.

Secrets live in HERDR_PLUGIN_CONFIG_DIR/.env (never in the plugin root):
DISCORD_BOT_TOKEN, DISCORD_ALLOWLIST_USER_IDS, optional DISCORD_GUILD_ID,
DISCORD_CATEGORY_NAME, DISCORD_NOTIFY_WEBHOOK.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from common import (  # noqa: E402
    STATE_DIR,
    agent_label_map,
    herdr_json,
    herdr_raw,
    load_channels,
    load_env,
    log,
    save_channels,
)

RECONCILE_SECONDS = 60
LOCK_PATH = Path("/tmp/herdr-agent-discord.lock")
MAX_TAIL_CHARS = 1800
_lock_handle = None


def acquire_singleton_lock() -> None:
    """Exit immediately if another bridge instance holds the lock (a normal,
    expected outcome when herdr's startup hook races the running bridge --
    the flock is what makes duplicate gateways structurally impossible)."""
    global _lock_handle
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _lock_handle = LOCK_PATH.open("w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another bridge instance holds the lock -- exiting")
        sys.exit(0)
    _lock_handle.write(str(os.getpid()))
    _lock_handle.flush()


async def am_i_orphaned(parent_pid_at_start: int) -> bool:
    if os.getppid() != parent_pid_at_start:
        log(f"orphaned (parent {parent_pid_at_start} -> {os.getppid()}); exiting")
        return True
    return False


def run() -> None:
    import discord  # venv-only dependency (setup.sh: pip install discord.py)
    from discord.ext import tasks

    load_env()
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        log("DISCORD_BOT_TOKEN missing -- bridge cannot start")
        raise SystemExit(1)
    allowlist = {
        x.strip()
        for x in os.environ.get("DISCORD_ALLOWLIST_USER_IDS", "").split(",")
        if x.strip()
    }
    category_name = os.environ.get("DISCORD_CATEGORY_NAME", "herdr agents")

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    parent_pid_at_start = os.getppid()

    def resolve_guild():
        gid = os.environ.get("DISCORD_GUILD_ID", "").strip()
        if gid:
            guild = client.get_guild(int(gid))
            if guild:
                return guild
            log(f"DISCORD_GUILD_ID {gid} not found among my guilds")
        if len(client.guilds) == 1:
            return client.guilds[0]
        log(f"cannot pick a guild (in {len(client.guilds)}); set DISCORD_GUILD_ID")
        return None

    async def ensure_channel(guild, label: str):
        category = discord.utils.get(guild.categories, name=category_name)
        if category is None:
            category = await guild.create_category(category_name)
        channel = discord.utils.get(category.text_channels, name=label)
        if channel is None:
            channel = await category.create_text_channel(label)
        return channel

    async def ensure_webhook(channel):
        for hook in await channel.webhooks():
            if hook.user and hook.user.id == client.user.id:
                return hook
        return await channel.create_webhook(name="herdr bridge")

    async def reconcile() -> None:
        guild = resolve_guild()
        if guild is None:
            return
        channels = load_channels()["channels"]
        changed = False
        for pane_id, (label, cwd) in sorted(agent_label_map().items()):
            entry = channels.get(label)
            if entry and entry.get("webhook_url") and entry.get("channel_id"):
                # keep the live pane id fresh for relay targeting
                if entry.get("pane_id") != pane_id:
                    entry["pane_id"] = pane_id
                    changed = True
                continue
            try:
                channel = await ensure_channel(guild, label)
                if channel is None:
                    continue
                hook = await ensure_webhook(channel)
                channels[label] = {
                    "channel_id": channel.id,
                    "webhook_url": hook.url,
                    "pane_id": pane_id,
                    "cwd": cwd,
                }
                changed = True
                log(f"provisioned #{label} for {pane_id}")
            except Exception as exc:
                log(f"provisioning failed for #{label}: {exc}")
        if changed:
            save_channels({"channels": channels})

    @tasks.loop(seconds=10)
    async def orphan_watch():
        if await am_i_orphaned(parent_pid_at_start):
            os._exit(0)  # herdr server died; its next start spawns a fresh bridge

    @tasks.loop(seconds=RECONCILE_SECONDS)
    async def reconcile_loop():
        try:
            await reconcile()
        except Exception as exc:
            log(f"reconcile error: {exc}")

    @client.event
    async def on_ready():
        log(f"bot ready as {client.user} in {[g.name for g in client.guilds]}")
        try:
            await reconcile()
        except Exception as exc:
            log(f"startup reconcile failed: {exc}")
        if not orphan_watch.is_running():
            orphan_watch.start()
        if not reconcile_loop.is_running():
            reconcile_loop.start()

    def find_agent(label: str):
        """(pane_id, cwd) for a live agent with this label, or (None, None)."""
        for pane_id, (lbl, cwd) in agent_label_map().items():
            if lbl == label:
                return pane_id, cwd
        return None, None

    def find_session_file(cwd: str):
        """Newest transcript for a cwd (mirrors omp-watch/omp-last)."""
        home = str(Path.home())
        key = cwd[len(home):] if cwd.startswith(home) else cwd
        key = key.replace("/", "-")
        d = Path.home() / ".omp/agent/sessions" / key
        if not d.is_dir():
            return None
        files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def transcript_contains(cwd: str, needle: str, since_byte: int) -> bool:
        """True if `needle` appeared in the transcript after `since_byte`
        -- unambiguous proof the submitted message landed in the session
        (status flips can't confirm a queued steer into a working agent)."""
        f = find_session_file(cwd)
        if f is None:
            return False
        try:
            size = f.stat().st_size
            if size <= since_byte:
                return False
            with f.open("rb") as fh:
                fh.seek(since_byte)
                return needle.encode() in fh.read()
        except OSError:
            return False

    async def relay_via_pane(pane_id: str, cwd: str, text: str) -> str:
        """Raw-deliver a message into a nested agent's REPL via pane
        send-text. Guarded: the pane's visible tail must show omp's input
        box (the model/Prewalk header row) -- otherwise the text would be
        typed into whatever nvim window has focus (the user's editor).
        Paste and Enter are sent as SEPARATE writes with a gap: the
        trailing \\r of a combined burst is swallowed (verified live
        2026-09-05 -- text landed in the input box, submit never fired).
        Returns "ok", "guard", or "unconfirmed"."""
        ok, out, _ = herdr_raw(
            "agent", "read", pane_id, "--source", "visible", "--lines", "10"
        )
        tail = (out or "")[-1200:]
        if not re.search(r"Prewalk|Opus|GLM|π", tail):
            log(f"relay_via_pane({pane_id}): REPL visibility guard failed")
            return "guard"
        sfile = find_session_file(cwd)
        since_byte = sfile.stat().st_size if sfile else 0
        needle = re.sub(r"\s+", " ", text.strip())[:24]
        payload = "\x1b[200~" + text + "\x1b[201~"
        ok, _, err = herdr_raw("pane", "send-text", pane_id, payload)
        if not ok:
            log(f"relay_via_pane({pane_id}): send-text failed: {err[:200]}")
            return "unconfirmed"
        await asyncio.sleep(0.3)
        herdr_raw("pane", "send-keys", pane_id, "enter")

        def delivered() -> bool:
            got, data, _ = herdr_json("agent", "get", pane_id)
            if got and ((data or {}).get("result", {}).get("agent", {}) or {}).get(
                "agent_status"
            ) == "working":
                return True
            return transcript_contains(cwd, needle, since_byte)

        for _ in range(4):
            await asyncio.sleep(2)
            if delivered():
                log(f"relay_via_pane({pane_id}): delivered")
                return "ok"
        # the first Enter can be dropped right after a paste block -- send
        # one more, then judge
        herdr_raw("pane", "send-keys", pane_id, "enter")
        for _ in range(3):
            await asyncio.sleep(2)
            if delivered():
                log(f"relay_via_pane({pane_id}): delivered on enter retry")
                return "ok"
        log(f"relay_via_pane({pane_id}): sent, no working transition observed")
        return "unconfirmed"

    @client.event
    async def on_message(message):
        if message.author.bot or message.guild is None:
            return
        if allowlist and str(message.author.id) not in allowlist:
            return
        channels = load_channels()["channels"]
        entry = next(
            (
                {"label": label, **v}
                for label, v in channels.items()
                if v.get("channel_id") == message.channel.id
            ),
            None,
        )
        if entry is None:
            return  # not an agent channel
        label = entry["label"]
        text = message.content.strip()

        if text.startswith("!status"):
            pane_id, _ = find_agent(label)
            if not pane_id:
                await message.reply(f"no live agent for #{label} right now.")
                return
            ok, data, _ = herdr_json("agent", "get", pane_id)
            agent = ((data or {}).get("result") or {}).get("agent") or {}
            embed = discord.Embed(
                title=label,
                color=0x3498DB,
                description=(
                    f"status: **{agent.get('agent_status', 'unknown')}**\n"
                    f"kind: {agent.get('agent', '?')} · pane: {pane_id}\n"
                    f"cwd: {agent.get('cwd', '?')}"
                ),
            )
            await message.reply(embed=embed)
            return

        if text.startswith("!tail"):
            pane_id, _ = find_agent(label)
            if not pane_id:
                await message.reply(f"no live agent for #{label} right now.")
                return
            digits = "".join(ch for ch in text[5:].strip() if ch.isdigit())
            n = max(1, min(int(digits or "15"), 50))
            ok, out, err = herdr_raw(
                "agent", "read", pane_id, "--source", "recent-unwrapped", "--lines", str(n)
            )
            body = (out if ok else err).strip() or "no output"
            await message.reply(f"```\n{body[:MAX_TAIL_CHARS]}\n```")
            return

        # plain message = relay into the agent
        pane_id, agent_cwd = find_agent(label)
        if not pane_id:
            await message.reply(f"no live agent for #{label} right now.")
            return
        async with message.channel.typing():
            ok, data, err = herdr_json("agent", "prompt", pane_id, text)
        if ok:
            await message.add_reaction("✅")
            return
        code = ""
        try:
            code = (json.loads(err).get("error") or {}).get("code", "")
        except Exception:
            pass
        if code == "agent_blocked":
            await message.reply("⛔ agent is blocked — approve its question in the pane first.")
            return

        # agent_not_ready is the nested-agent case: omp runs inside the
        # pane's nvim (yarepl float), so it is never the pane's foreground
        # process and `agent prompt` refuses deterministically (verified
        # live 2026-09-05; there is no force flag). Fall back to the pane
        # surface: paste-wrapped send-text, guarded by a visibility check.
        if code == "agent_not_ready":
            outcome = await relay_via_pane(pane_id, agent_cwd, text)
            if outcome == "ok":
                await message.add_reaction("✅")
            elif outcome == "guard":
                await message.reply(
                    "⚠️ the omp REPL window doesn't look focused/open in that pane — "
                    "refusing to type blind (the text could land in your editor). "
                    "Open the REPL (ctrl-a) and resend."
                )
            else:
                await message.add_reaction("👀")
            return

        if code == "agent_prompt_stalled":
            # verified live: the text IS delivered even when the lifecycle
            # check stalls (e.g. the agent errors instead of transitioning)
            await message.add_reaction("👀")
        else:
            log(f"relay to {pane_id} failed: {err[:200]}")
            await message.reply(f"relay failed: `{(err or 'unknown error')[:200]}`")

    client.run(token, log_handler=None)


def main() -> None:
    acquire_singleton_lock()
    while True:
        try:
            run()
        except SystemExit as exc:
            if exc.code == 1:  # config missing -- retry later, don't spin
                log("run() exited with config error; retrying in 60s")
                time.sleep(60)
                continue
            raise
        except Exception as exc:
            import traceback

            log(f"bridge crashed: {exc}; restarting in 5s\n{traceback.format_exc()}")
            time.sleep(5)


if __name__ == "__main__":
    main()
