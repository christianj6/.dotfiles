#!/usr/bin/env python3
"""Keep every claude pane's roster name at claude-v<major>-<pane>.

The pane suffix matches omp-watch's omp-v<N>-<pane>, and doubles as the
uniqueness guarantee herdr requires of live agent names. Unlike omp-watch, this
replaces ANY non-matching name, hand-given ones included: the plugin owns
claude naming. Panes that are mid-turn are left for a later tick.

Run with no arguments in the foreground, or with --daemon to detach. See
herdr-plugin.toml for what launches it.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional

POLL_SECONDS = 5
# Consecutive failed ticks before a daemon decides the server is gone and exits,
# freeing the lock for the next start. Same role as omp-watch's constant.
SERVER_DEATH_TICKS = 10
# Mid-turn states. "blocked" is a turn waiting on a dialog, so it counts.
UNSETTLED = {"working", "blocked"}

HERDR_BIN = os.environ.get("HERDR_BIN_PATH", "herdr")
LOCK_PATH = Path("/tmp/claude-name.lock")
LOG_PATH = "/tmp/claude-name-daemon.log"
# Module-level on purpose: a local would be collected, closing the fd and
# releasing the flock straight after acquiring it.
_lock_handle: Optional[object] = None


def log(msg: str) -> None:
    print(f"[claude-name] {time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


def acquire_singleton_lock() -> None:
    """Exit quietly if another instance holds the lock. The event hook relies
    on this: most of its launches are meant to do nothing."""
    global _lock_handle
    _lock_handle = open(LOCK_PATH, "a")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
    _lock_handle.truncate(0)
    _lock_handle.write(str(os.getpid()))
    _lock_handle.flush()


def parse_major(version_output: str) -> Optional[str]:
    match = re.match(r"\s*(\d+)\.", version_output)
    return match.group(1) if match else None


def pane_suffix(pane_id: str) -> str:
    return pane_id.replace(":", "").lower()


def target_name(pane_id: str, major: Optional[str]) -> str:
    suffix = pane_suffix(pane_id)
    return f"claude-v{major}-{suffix}" if major else f"claude-{suffix}"


def rename_needed(agent: Dict, major: Optional[str]) -> Optional[str]:
    """The name this agent should be given now, or None to leave it alone."""
    if agent.get("agent") != "claude" or agent.get("agent_status") in UNSETTLED:
        return None
    target = target_name(agent["pane_id"], major)
    return None if agent.get("name") == target else target


def claude_env() -> Dict[str, str]:
    """Without HERDR_*, so a claude process can never claim a pane. See
    NEVER let a nested agent CLI claim your pane in herdr-workstreams."""
    return {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}


def claude_bin() -> str:
    # Plugin processes may not have ~/.local/bin on PATH.
    return shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")


def read_major() -> Optional[str]:
    try:
        proc = subprocess.run(
            [claude_bin(), "--version"], capture_output=True, text=True,
            timeout=10, env=claude_env(), stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return parse_major(proc.stdout) if proc.returncode == 0 else None


def list_agents() -> list:
    proc = subprocess.run(
        [HERDR_BIN, "agent", "list"], capture_output=True, text=True, timeout=10
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "agent list failed")
    return json.loads(proc.stdout)["result"]["agents"]


def rename(pane_id: str, name: str) -> Optional[str]:
    """Error text, or None on success."""
    proc = subprocess.run(
        [HERDR_BIN, "agent", "rename", pane_id, name],
        capture_output=True, text=True, timeout=10,
    )
    return None if proc.returncode == 0 else (proc.stderr or proc.stdout).strip()


class Naming:
    def __init__(self) -> None:
        # A brief failure keeps the known version: otherwise every pane would
        # flip to the fallback name and back.
        self.major: Optional[str] = None
        self.major_failed = False
        # pane -> name that failed, so a stuck rename logs once, not every tick.
        self.failed: Dict[str, str] = {}

    def refresh_major(self) -> None:
        major = read_major()
        if major:
            self.major, self.major_failed = major, False
        elif not self.major_failed:
            self.major_failed = True
            log(f"claude --version failed; using {self.major or 'the unversioned name'}")

    def tick(self) -> None:
        self.refresh_major()
        for agent in list_agents():
            target = rename_needed(agent, self.major)
            if not target:
                continue
            pane_id = agent["pane_id"]
            error = rename(pane_id, target)
            if error is None:
                self.failed.pop(pane_id, None)
                log(f"{pane_id}: {agent.get('name')!r} -> {target!r}")
            elif self.failed.get(pane_id) != target:
                self.failed[pane_id] = target
                log(f"{pane_id}: rename to {target!r} failed: {error}")


def run() -> None:
    naming = Naming()
    tick_errors = 0
    while True:
        try:
            naming.tick()
            tick_errors = 0
        except Exception as exc:  # one bad tick must not end the loop
            tick_errors += 1
            if tick_errors == 1:
                log(f"tick failed: {exc}")
            if tick_errors >= SERVER_DEATH_TICKS:
                log("herdr unreachable for too long; exiting")
                return
        time.sleep(POLL_SECONDS)


def daemonize() -> None:
    """Double-fork so the instance outlives the short-lived hook process."""
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
    if "--daemon" in sys.argv:
        daemonize()
    acquire_singleton_lock()
    run()
