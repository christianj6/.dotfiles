"""One singleton lock for every long-running herdr plugin daemon.

Used by lifeview-fallback, claude-name, agent-discord and omp-watch. Import it
from a plugin's entry script (run from the plugin dir) with:

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
    from singleton import SingletonLock, plugin_state_dir

Why it exists. An flock is mutual exclusion on an inode, not on a path. The
plugins used to lock files under /tmp, and macOS prunes /tmp: the file a
running daemon had locked got unlinked, the next launch created a new file at
the same path, its flock succeeded on the new inode, and two daemons ran as
"the singleton" (duplicate prescient tasks from lifeview, 2026-11-18; two
claude-name daemons and an unlinked agent-discord lock on the same day).

So:
  - paths live under ~/.local/state/herdr/plugins/<plugin-id>/, never /tmp,
    and are fixed per plugin id (not HERDR_PLUGIN_STATE_DIR: a launch from
    another context, e.g. workspace-up run from a pane, must find the same lock);
  - acquire() verifies the path still names the inode it locked;
  - keep(), called every tick, re-takes a removed or replaced path, or reports
    that another instance now holds it so the caller exits.
One daemon survives either way, and a launch after a re-take exits on the lock.
"""

from __future__ import annotations

import fcntl
import os
import sys
import time
from pathlib import Path
from typing import Callable, Optional

STATE_ROOT = Path.home() / ".local" / "state" / "herdr" / "plugins"


def plugin_state_dir(plugin_id: str) -> Path:
    """~/.local/state/herdr/plugins/<plugin-id> (not created here)."""
    return STATE_ROOT / plugin_id


def _stderr(msg: str) -> None:
    print(f"[singleton] {time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


class SingletonLock:
    """An flock that is only held while the path still names the locked inode."""

    def __init__(self, path: Path, log: Callable[[str], None] = _stderr):
        self.path = Path(path)
        self.log = log
        self.fh = None

    def _ours(self, fh) -> bool:
        try:
            st, mine = os.stat(self.path), os.fstat(fh.fileno())
        except OSError:
            return False
        return (st.st_dev, st.st_ino) == (mine.st_dev, mine.st_ino)

    def _take(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            return None
        if not self._ours(fh):            # replaced between open and flock
            fh.close()
            return None
        fh.truncate(0)
        fh.write(str(os.getpid()))
        fh.flush()
        return fh

    def acquire(self) -> bool:
        """True if we are now the singleton; False if another instance is."""
        self.fh = self._take()
        return self.fh is not None

    def keep(self) -> bool:
        """Call every tick. True while we hold the lock the path names
        (re-taking it if the path was removed or replaced and nobody else
        holds it); False means another instance holds it: exit."""
        if self.fh is None:
            return False
        if self._ours(self.fh):
            return True
        fh = self._take()
        if fh is None:
            self.log(f"lock path {self.path} now held by another instance; exiting")
            return False
        old, self.fh = self.fh, fh
        old.close()
        self.log(f"lock path {self.path} was removed or replaced; re-took it")
        return True

    def release(self) -> None:
        if self.fh is not None:
            self.fh.close()
            self.fh = None


def acquire_or_exit(path: Path, log: Callable[[str], None] = _stderr,
                    quiet: bool = True) -> SingletonLock:
    """The entry-point shape every plugin uses: the lock, or exit 0."""
    lock = SingletonLock(path, log)
    if not lock.acquire():
        if not quiet:
            log(f"another instance holds {path} -- exiting")
        sys.exit(0)
    return lock
