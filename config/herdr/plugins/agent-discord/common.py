"""Shared plumbing for the agent-discord plugin (notify hook + Discord bot).

Only stdlib. Both entrypoints run with the plugin directory as cwd and get
HERDR_PLUGIN_CONFIG_DIR / HERDR_PLUGIN_STATE_DIR injected by herdr; the
fallbacks below match herdr's default layout for local development runs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

HERDR = os.environ.get("HERDR_BIN_PATH", "herdr")
PLUGIN_ID = os.environ.get("HERDR_PLUGIN_ID", "dotfiles.agent-discord")
CONFIG_DIR = Path(
    os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    or Path.home() / ".config/herdr/plugins/config" / PLUGIN_ID
)
STATE_DIR = Path(
    os.environ.get("HERDR_PLUGIN_STATE_DIR")
    or Path.home() / ".local/state/herdr/plugins" / PLUGIN_ID
)
STATE_FILE = STATE_DIR / "channels.json"
LOG_FILE = STATE_DIR / "bridge.log"
LOG_MAX_BYTES = 1_000_000

NOTIFY_STATUSES = ("done", "blocked")  # anything else stays silent


def parse_env_value(raw: str) -> str:
    """A .env value: quotes stripped, and a trailing ` # comment` dropped
    (.env.example puts a short comment after each key; `KEY=   # required`
    must read as EMPTY, not as the comment text)."""
    v = raw.strip()
    if v[:1] in ("'", '"'):
        end = v.find(v[0], 1)
        return v[1:end] if end > 0 else v[1:]
    m = re.search(r"(^|\s)#", v)
    if m:
        v = v[: m.start()]
    return v.strip()


def load_env(files: "list[Path] | None" = None) -> None:
    """Seed os.environ from the plugin's .env files (never overrides real
    env vars). Two locations are honored, in priority order: the herdr
    config dir (the documented home for credentials) and the plugin root
    next to the code -- that is where the .env.example template lives, and
    the natural place to fill it in first; it is gitignored so a token
    there cannot leak into the repo."""
    if files is None:
        files = [CONFIG_DIR / ".env", Path(__file__).resolve().parent / ".env"]
    for path in files:
        if not path.is_file():
            continue
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = parse_env_value(value)
            # An EMPTY value is a template line, not a setting: it must not
            # shadow a later file's real value. The config dir's .env held a
            # copied `DISCORD_BOT_TOKEN=` (empty) and blocked the plugin
            # root's real token, so the bot never started ("DISCORD_BOT_TOKEN
            # missing" every 60 s) while webhook notifications kept working.
            # An empty real env var counts as unset for the same reason.
            if key and value and not os.environ.get(key):
                os.environ[key] = value


def log(msg: str) -> None:
    """Append a line to the bridge log with a 1MB single-file rotation."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            LOG_FILE.replace(LOG_FILE.with_suffix(".log.old"))
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a") as f:
            f.write(f"[{stamp}] {msg}\n")
    except OSError:
        pass


def herdr_raw(*args: str) -> tuple[bool, str, str]:
    """(ok, raw_stdout, raw_stderr) -- for commands that print plain text
    (e.g. `agent read`). herdr CLI errors are JSON on stderr with exit 1."""
    try:
        result = subprocess.run(
            [HERDR, *args], capture_output=True, text=True, timeout=20
        )
    except Exception as exc:  # transport/spawn hiccup -- keep callers alive
        log(f"herdr call failed {args}: {exc}")
        return False, "", str(exc)
    return result.returncode == 0, result.stdout, result.stderr.strip()


def find_session_file(cwd: str):
    """Newest transcript for a cwd. omp's dir naming, fully mapped against
    all six live dirs 2026-09-06: HOME-relative cwds keep their leading
    slash (/.dotfiles -> -.dotfiles); absolute cwds outside HOME are
    dash-wrapped on BOTH ends (/private/tmp/x -> --private-tmp-x--), so
    the plain key alone never matched them (found live when a /tmp-cwd
    test agent's blocked embed came out empty)."""
    home = str(Path.home())
    key = cwd[len(home):] if cwd.startswith(home) else cwd
    key = key.replace("/", "-")
    base = Path.home() / ".omp/agent/sessions"
    candidates = [key] if cwd.startswith(home) else [
        "--" + cwd.strip("/").replace("/", "-") + "--", key]
    for k in candidates:
        d = base / k
        if d.is_dir():
            files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                return files[0]
    return None


def latest_report(cwd: str, max_chars: int = 1800) -> str:
    """The text of the newest assistant message with actual report text --
    i.e. what the agent last SAID (its final answer / interim status),
    straight from the transcript, with no TUI chrome. Empty string when
    no text-bearing assistant entry is found. The window expands
    adaptively: heavy turns with huge tool outputs (screenshots, schema
    dumps) can push the last report megabytes back from EOF."""
    f = find_session_file(cwd)
    if f is None:
        return ""
    try:
        size = f.stat().st_size
    except OSError:
        return ""

    def extract(window: int) -> str:
        with f.open("rb") as fh:
            if size > window:
                fh.seek(size - window)
                fh.readline()  # drop a possibly-truncated first line
            data = fh.read()
        for line in reversed(data.decode("utf-8", "ignore").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = e.get("message") or {}
            if e.get("type") != "message" or msg.get("role") != "assistant":
                continue
            text = "\n".join(
                c.get("text", "")
                for c in (msg.get("content") or [])
                if isinstance(c, dict) and c.get("type") == "text"
            ).strip()
            if text:
                text = re.sub(r"\n{3,}", "\n\n", text)
                return text[:max_chars] + ("…" if len(text) > max_chars else "")
        return ""

    for window in (262_144, 1_048_576, 4_194_304, 16_777_216):
        if window >= size:
            return extract(size)  # whole file
        result = extract(window)
        if result:
            return result
    return extract(16_777_216)


def latest_error(cwd: str, max_chars: int = 600) -> str:
    """Newest assistant errorMessage from the session transcript -- the
    model/provider failure text (e.g. OpenRouter's guardrail 404). Empty
    string when the transcript has none (e.g. a herdr-native approval
    block), so callers can fall back to latest_report(). Bounded tail read:
    when an agent is blocked the failing entry is the newest thing in the
    file; 1MB covers it without the adaptive window latest_report needs."""
    f = find_session_file(cwd)
    if f is None:
        return ""
    try:
        with f.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 1_048_576))
            data = fh.read().decode("utf-8", "ignore")
    except OSError:
        return ""
    lines = data.splitlines()
    if data and not data.endswith("\n"):
        lines = lines[:-1]  # torn final line: writer mid-flush, skip
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = e.get("message") or {}
        if e.get("type") == "message" and msg.get("role") == "assistant" and msg.get("errorMessage"):
            text = str(msg["errorMessage"]).strip()
            return text[:max_chars] + ("…" if len(text) > max_chars else "")
    return ""


def herdr_json(*args: str) -> tuple[bool, dict | None, str]:
    """Run a herdr CLI call; return (ok, parsed_stdout_or_None, stderr).

    The parsed error body matters to callers (agent_blocked vs
    agent_prompt_stalled vs transport failures), so stderr is surfaced.
    """
    ok, stdout, stderr = herdr_raw(*args)
    parsed = None
    if stdout.strip():
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
    return ok, parsed, stderr


def sanitize_label(name: str) -> str:
    """Discord channel-name-safe project label."""
    s = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return s[:90] or "agent"


def herdr_agents() -> list[dict]:
    """The live herdr agent listing ([] when herdr does not answer)."""
    ok, data, _ = herdr_json("agent", "list")
    if not ok or not data:
        return []
    return (data.get("result") or {}).get("agents") or []


def label_map_of(agents: list[dict]) -> dict[str, tuple[str, str]]:
    """agent_label_map() over a given listing (pure: tests pass a fake one)."""
    base: dict[str, list[tuple[str, str, str]]] = {}
    for a in agents:
        cwd = a.get("cwd") or ""
        pane_id = a.get("pane_id")
        if not cwd or not pane_id:
            continue
        label = sanitize_label(Path(cwd).name)
        base.setdefault(label, []).append((pane_id, cwd, a.get("workspace_id") or ""))
    out: dict[str, tuple[str, str]] = {}
    for label, entries in base.items():
        if len(entries) == 1:
            pane_id, cwd, _ = entries[0]
            out[pane_id] = (label, cwd)
        else:
            for pane_id, cwd, ws in entries:
                out[pane_id] = (f"{label}-{ws or 'x'}", cwd)
    return out


def resolve_agent(label: str, agents: list[dict] | None = None) -> dict | None:
    """The live agent a channel label means, resolved NOW from herdr's listing;
    never from a stored pane id (those go stale on every rollout: wD:p1,
    w5:p8, ... in channels.json). Returns the listing's entry, or None.

    A project usually has TWO agents (its omp coordinator and its Claude), and
    agent_label_map() suffixes both ("dotfiles-wD"), so a channel's stored
    label rarely matches a live one exactly. Tried in order, first hit wins:
      1. the exact live label (a single-agent project's plain label, or a
         suffixed channel such as #dotfiles-wD);
      2. the project's plain label ("dotfiles" -> every agent whose project
         folder is dotfiles);
      3. a suffixed label from an older layout ("dotfiles-w6" -> dotfiles).
    Within a step the COORDINATOR (omp) is preferred: a Discord message is a
    request to the project, and the omp decides what happens to it; handing it
    to the Claude would bypass the coordinator.
    """
    agents = herdr_agents() if agents is None else agents
    live = label_map_of(agents)
    by_pane = {a.get("pane_id"): a for a in agents}

    def base_of(pane: str) -> str:
        return sanitize_label(Path(live[pane][1]).name)

    m = re.match(r"^(.+)-w[0-9A-Za-z]+$", label)
    steps = [
        lambda p: live[p][0] == label,
        lambda p: base_of(p) == label,
        lambda p: bool(m) and base_of(p) == m.group(1),
    ]
    for match in steps:
        hits = [by_pane[p] for p in live if match(p)]
        if hits:
            return sorted(hits, key=lambda a: (a.get("agent") != "omp", a.get("pane_id") or ""))[0]
    return None


def agent_label_map() -> dict[str, tuple[str, str]]:
    """{pane_id: (label, cwd)} for every registered agent.

    The label is the project directory basename -- the identity the user
    actually thinks in (heinzel, thor-voiceai, ...). Collisions (two live
    agents in same-named directories) get the workspace id appended so
    both keep a distinct channel.
    """
    return label_map_of(herdr_agents())


def load_channels() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text())
        if isinstance(data, dict) and isinstance(data.get("channels"), dict):
            return data
    except Exception:
        pass
    return {"channels": {}}


def save_channels(data: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(STATE_FILE)
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:
        pass
