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


def load_env() -> None:
    """Seed os.environ from the plugin's .env files (never overrides real
    env vars). Two locations are honored, in priority order: the herdr
    config dir (the documented home for credentials) and the plugin root
    next to the code -- that is where the .env.example template lives, and
    the natural place to fill it in first; it is gitignored so a token
    there cannot leak into the repo."""
    roots = [CONFIG_DIR, Path(__file__).resolve().parent]
    for root in roots:
        path = root / ".env"
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
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
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


def agent_label_map() -> dict[str, tuple[str, str]]:
    """{pane_id: (label, cwd)} for every registered agent.

    The label is the project directory basename -- the identity the user
    actually thinks in (heinzel, thor-voiceai, ...). Collisions (two live
    agents in same-named directories) get the workspace id appended so
    both keep a distinct channel.
    """
    ok, data, _ = herdr_json("agent", "list")
    if not ok or not data:
        return {}
    agents = (data.get("result") or {}).get("agents") or []
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
