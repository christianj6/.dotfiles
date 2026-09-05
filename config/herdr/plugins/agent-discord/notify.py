#!/usr/bin/env python3
"""herdr [[events]] hook: pane.agent_status_changed -> Discord webhook.

Short-lived, stdlib-only: herdr spawns one instance per agent status
transition and this script posts to the agent's channel webhook and exits.

Ping semantics: a message fires when a pane's PREVIOUS status was
"working" and it has now settled (idle/done) or needs approval (blocked).
Herdr only renders "done" for UNVIEWED panes -- a pane the user is
watching goes straight to "idle" -- so keying the ping on the
working->settled transition instead of the literal "done" string makes
the ping fire regardless of where the user is looking. done->idle (user
viewed after a ping) and idle->idle stay silent. Falls back to
DISCORD_NOTIFY_WEBHOOK when no per-agent channel exists yet.
"""

from __future__ import annotations

import fcntl
import json
import os
import urllib.request

from common import (
    STATE_DIR,
    agent_label_map,
    load_channels,
    load_env,
    log,
)

COLORS = {"done": 0x2ECC71, "blocked": 0xE67E22, "idle": 0x2ECC71}
DESCRIPTIONS = {
    "done": "turn finished — awaiting input",
    "idle": "turn finished — awaiting input",
    "blocked": "needs your approval",
}


def webhook_post(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            # Discord's edge rejects urllib's default "Python-urllib/x.y"
            # User-Agent with 403 (verified live 2026-09-05: identical
            # payload -> 403 with the default UA, 204 with a real one).
            "User-Agent": "herdr-agent-discord (local bridge, 1.0)",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"webhook returned HTTP {resp.status}")


def load_prev_status() -> dict:
    try:
        return json.loads((STATE_DIR / "last_status.json").read_text())
    except Exception:
        return {}


def save_prev_status(prev: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / "last_status.json.tmp"
    tmp.write_text(json.dumps(prev))
    tmp.replace(STATE_DIR / "last_status.json")


def should_notify(prev: dict, pane_id: str, new_status: str) -> bool:
    return prev.get(pane_id) == "working" and new_status in ("done", "idle", "blocked")


def main() -> None:
    load_env()
    raw = os.environ.get("HERDR_PLUGIN_EVENT_JSON")
    if not raw:
        return
    try:
        event = json.loads(raw).get("data") or {}
    except json.JSONDecodeError:
        log(f"unparseable HERDR_PLUGIN_EVENT_JSON: {raw[:200]}")
        return
    status = event.get("agent_status")
    pane_id = event.get("pane_id") or "unknown-pane"
    if not status:  # released / exited -- out of notify scope
        return

    # prev-state read/modify/write under an flock: two agents can settle
    # in the same second and each hook is a separate process.
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = (STATE_DIR / "last_status.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prev = load_prev_status()
        was_working = should_notify(prev, pane_id, status)
        prev[pane_id] = status
        save_prev_status(prev)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
    if not was_working:
        return

    label, cwd = agent_label_map().get(pane_id, ("unknown-agent", ""))
    entry = load_channels()["channels"].get(label) or {}
    url = entry.get("webhook_url") or os.environ.get("DISCORD_NOTIFY_WEBHOOK")
    if not url:
        log(f"no webhook for #{label} ({pane_id}); {status} notification dropped")
        return

    body = {
        "username": "herdr",
        "allowed_mentions": {"parse": []},
        "embeds": [
            {
                "title": f"{'⛔' if status == 'blocked' else '✅'} {label} — {status}",
                "description": DESCRIPTIONS.get(status, "status change"),
                "color": COLORS.get(status, 0x3498DB),
                "footer": {"text": f"{pane_id} · {cwd}" if cwd else pane_id},
            }
        ],
    }
    try:
        webhook_post(url, body)
        log(f"notified #{label}: {status} ({pane_id})")
    except Exception as exc:
        log(f"webhook post failed for #{label} ({pane_id}, {status}): {exc}")


if __name__ == "__main__":
    main()
