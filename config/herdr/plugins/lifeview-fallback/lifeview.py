#!/usr/bin/env python3
"""Fallback entries in each project's prescient-status.json, from herdr's state.

prescient's life view reads <repo>/prescient-status.json for what each agent
is at. Agents write it themselves (`prescient status ...`); this fills the gap
when one has not spoken yet, forgot, or let its word go stale, so its icon
still means something.

Rules (the agent's own word always wins):
- Entries are keyed by pane id, as `prescient status` keys them, so an
  agent's next write replaces ours in place.
- Ours carry "by": "fallback" (prescient reads state/line/at and ignores
  other keys) and a "fallback: ..." line.
- An agent-authored entry is never touched while fresh: younger than
  AGENT_FRESH_S, or within its own ttl_s. Past that, only a `working`
  herdr no longer corroborates is replaced; idle/standby/blocked stand
  until the agent replaces them (see compatible()).
- herdr "unknown" or absent says nothing, so nothing is written for it.
- Ours are removed once the agent has its own entry under its name, or
  once its pane is gone from herdr.
- Writes take prescient's lock (.prescient-status.json.lock) and replace
  the file whole, re-reading under the lock, like write_status() does.
- Only repos that already gitignore prescient-status.json are written to,
  so no repo gains a stray tracked file.

Run with no arguments in the foreground, or with --daemon to detach. See
herdr-plugin.toml for what launches it.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

POLL_SECONDS = 10
SERVER_DEATH_TICKS = 10      # consecutive failed ticks before a daemon exits (as in claude-name)
AGENT_FRESH_S = 180          # an agent's own entry younger than this is never touched
FALLBACK_WORKING_TTL = 300   # s: covers herdr's blind spot; refreshed while herdr still says working
STATUS_FILE = "prescient-status.json"
BY = "fallback"

# herdr agent_status -> (state, line) for the fallback entry
FROM_HERDR = {
    "working": ("working", "fallback: herdr reports working"),
    "idle": ("idle", "fallback: herdr idle"),
    "done": ("idle", "fallback: herdr idle"),
    "blocked": ("blocked", "fallback: herdr blocked (approval dialog?)"),
}

HERDR_BIN = os.environ.get("HERDR_BIN_PATH", "herdr")
LOCK_PATH = Path("/tmp/lifeview-fallback.lock")
LOG_PATH = "/tmp/lifeview-fallback.log"
_lock_handle: Optional[object] = None   # module-level so the flock outlives acquire()


def log(msg: str) -> None:
    print(f"[lifeview-fallback] {time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


def acquire_singleton_lock() -> None:
    global _lock_handle
    _lock_handle = open(LOCK_PATH, "a")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
    _lock_handle.truncate(0)
    _lock_handle.write(str(os.getpid()))
    _lock_handle.flush()


# ---- pure decision logic (unit-tested) ----

def age_s(entry: Dict, now: float) -> Optional[float]:
    try:
        at = datetime.fromisoformat(str(entry.get("at")))
    except (TypeError, ValueError):
        return None
    if at.tzinfo is None:
        at = at.astimezone()      # naive: local time
    return now - at.timestamp()


def is_ours(entry: object) -> bool:
    return isinstance(entry, dict) and entry.get("by") == BY


def agent_fresh(entry: Dict, now: float) -> bool:
    age = age_s(entry, now)
    if age is None:
        return False
    if entry.get("ttl_s"):
        try:
            if age <= float(entry["ttl_s"]):
                return True
        except (TypeError, ValueError):
            pass
    return age < AGENT_FRESH_S


def compatible(state: str, herdr: str) -> bool:
    """Does a stale agent entry still stand against herdr's word? Only a
    `working` herdr no longer corroborates falls (prescient stops believing
    it past its 120 s grace anyway). idle/standby/blocked always stand:
    prescient believes them until replaced, and herdr's own "working" is
    known to stick for hours on omp panes, so it must not overrule an
    agent's settled word."""
    if state == "working":
        return herdr in ("working", "unknown")
    return True


def decide(agent: Dict, entries: Dict, now: float) -> Tuple[str, Optional[Dict]]:
    """What to do with one agent's entries: ("keep", None), ("write", entry)
    under its pane id, or ("drop", None) to remove our pane-id entry."""
    pane, name = agent.get("pane_id") or "", agent.get("name") or ""
    herdr = agent.get("agent_status") or "unknown"
    by_name = entries.get(name) if name and name != pane else None
    by_pane = entries.get(pane)

    # The agent's own word under its name: prescient reads that first, so a
    # pane-id fallback is a second source of truth. Leave the name entry alone.
    if isinstance(by_name, dict) and not is_ours(by_name):
        return ("drop", None) if is_ours(by_pane) else ("keep", None)

    if isinstance(by_pane, dict) and not is_ours(by_pane) and by_pane.get("state"):
        if agent_fresh(by_pane, now) or compatible(str(by_pane.get("state")), herdr):
            return ("keep", None)

    if herdr not in FROM_HERDR:
        return ("keep", None)          # unknown/absent: herdr has nothing to say
    state, line = FROM_HERDR[herdr]
    if is_ours(by_pane) and by_pane.get("state") == state:
        age = age_s(by_pane, now)
        if state != "working" or (age is not None and age < FALLBACK_WORKING_TTL / 2):
            return ("keep", None)
    entry = {"state": state, "at": datetime.now().astimezone().isoformat(timespec="seconds"), "line": line, "by": BY}
    if state == "working":
        entry["ttl_s"] = float(FALLBACK_WORKING_TTL)
    return ("write", entry)


def plan(agents: list, entries: Dict, live_panes: set, now: float) -> Dict[str, Optional[Dict]]:
    """Key -> new entry (None: delete) for one status file."""
    changes: Dict[str, Optional[Dict]] = {}
    for a in agents:
        action, entry = decide(a, entries, now)
        if action == "write":
            changes[a["pane_id"]] = entry
        elif action == "drop":
            changes[a["pane_id"]] = None
    for key, e in entries.items():      # ours, for panes herdr no longer lists
        if is_ours(e) and key not in live_panes and key not in changes:
            changes[key] = None
    return changes


# ---- herdr + filesystem ----

def list_agents() -> list:
    proc = subprocess.run([HERDR_BIN, "agent", "list"], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "agent list failed")
    return json.loads(proc.stdout)["result"]["agents"]


def repo_root(cwd: str) -> Optional[str]:
    """The git toplevel of cwd, as `prescient status` resolves it, if the repo
    already gitignores the status file and its sidecars; else None."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
        if top.returncode != 0:
            return None
        root = top.stdout.strip()
        # check-ignore prints each ignored path; both must be (the lock is
        # created next to the file)
        ign = subprocess.run(["git", "-C", root, "check-ignore", STATUS_FILE, "." + STATUS_FILE + ".lock"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return root if len(ign.stdout.split()) == 2 else None


def read_entries(path: Path) -> Tuple[Dict, Dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    agents = raw.get("agents") if isinstance(raw.get("agents"), dict) else {}
    return raw, agents


def apply(root: str, agents: list, live_panes: set) -> None:
    """Re-read and decide under prescient's lock, so an agent's write between
    our look and our write is never clobbered."""
    path = Path(root) / STATUS_FILE
    _, peek = read_entries(path)
    if not plan(agents, peek, live_panes, time.time()):
        return                          # nothing to do: don't touch the lock
    with open(path.with_name("." + STATUS_FILE + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        raw, entries = read_entries(path)
        changes = plan(agents, entries, live_panes, time.time())
        if not changes:
            return
        for key, entry in changes.items():
            if entry is None:
                entries.pop(key, None)
                log(f"{root}: {key} fallback removed")
            else:
                entries[key] = entry
                log(f"{root}: {key} -> {entry['state']} ({entry['line']})")
        tmp = path.with_name("." + STATUS_FILE + ".tmp")
        tmp.write_text(json.dumps({**raw, "agents": entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)


class Fallback:
    def __init__(self) -> None:
        self.failed: Dict[str, str] = {}   # root -> last error, so a stuck repo logs once

    def tick(self) -> None:
        agents = list_agents()
        live = {a.get("pane_id") for a in agents if a.get("pane_id")}
        by_root: Dict[str, list] = {}
        for a in agents:
            if not a.get("pane_id"):
                continue
            root = repo_root(a.get("cwd") or "")
            if root:
                by_root.setdefault(root, []).append(a)
        for root, group in by_root.items():
            try:
                apply(root, group, live)
                self.failed.pop(root, None)
            except Exception as exc:       # one repo must not stop the rest
                if self.failed.get(root) != str(exc):
                    self.failed[root] = str(exc)
                    log(f"{root}: {exc}")


def run() -> None:
    fb = Fallback()
    tick_errors = 0
    while True:
        try:
            fb.tick()
            tick_errors = 0
        except Exception as exc:
            tick_errors += 1
            if tick_errors == 1:
                log(f"tick failed: {exc}")
            if tick_errors >= SERVER_DEATH_TICKS:
                log("herdr unreachable for too long; exiting")
                return
        time.sleep(POLL_SECONDS)


def daemonize() -> None:
    if os.fork():
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)
    log_fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    for fd in (0, 1, 2):
        os.dup2(log_fd, fd)
    if log_fd > 2:
        os.close(log_fd)


if __name__ == "__main__":
    if "--once" in sys.argv:
        Fallback().tick()
        sys.exit(0)
    if "--daemon" in sys.argv:
        daemonize()
    acquire_singleton_lock()
    run()
