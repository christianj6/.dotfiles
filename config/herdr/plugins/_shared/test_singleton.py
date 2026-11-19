#!/usr/bin/env python3
"""Tests for the shared singleton lock: python3 test_singleton.py

flock is per open file description, so two SingletonLock objects in one
process contend exactly like two daemons. The consumer section checks that
each of the four plugins uses this module with lock and log paths off /tmp.
"""

import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import singleton as sg  # noqa: E402

PLUGINS = HERE.parent


class Lock(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.path = Path(d.name, "sub", "lock")         # parent created on demand
        self.held = []
        self.logs = []
        self.addCleanup(lambda: [l.release() for l in self.held])

    def lock(self):
        l = sg.SingletonLock(self.path, self.logs.append)
        self.held.append(l)
        return l

    def replace_path(self):
        self.path.unlink()                                # what /tmp pruning did
        self.path.write_text("")

    def test_same_inode_second_instance_exits(self):
        first = self.lock()
        self.assertTrue(first.acquire())
        self.assertEqual(self.path.read_text(), str(os.getpid()))
        self.assertFalse(self.lock().acquire())
        self.assertTrue(first.keep())

    def test_replaced_path_newcomer_exits_after_the_holder_retakes(self):
        first = self.lock()
        self.assertTrue(first.acquire())
        self.replace_path()
        self.assertTrue(first.keep())
        self.assertIn("re-took it", self.logs[-1])
        self.assertFalse(self.lock().acquire())

    def test_removed_path_is_retaken(self):
        first = self.lock()
        self.assertTrue(first.acquire())
        self.path.unlink()
        self.assertTrue(first.keep())
        self.assertFalse(self.lock().acquire())

    def test_newcomer_that_won_the_replaced_path_makes_the_old_holder_exit(self):
        first = self.lock()
        self.assertTrue(first.acquire())
        self.replace_path()
        second = self.lock()
        self.assertTrue(second.acquire())
        self.assertFalse(first.keep())
        self.assertIn("held by another instance", self.logs[-1])
        self.assertTrue(second.keep())

    def test_acquire_refuses_a_path_replaced_between_open_and_flock(self):
        l = self.lock()
        self.path.parent.mkdir(parents=True)
        real = sg.fcntl.flock

        def flock_then_replace(fh, op):
            real(fh, op)
            self.replace_path()
        sg.fcntl.flock = flock_then_replace
        try:
            self.assertFalse(l.acquire())
        finally:
            sg.fcntl.flock = real

    def test_acquire_or_exit_exits_zero_when_held(self):
        first = self.lock()
        self.assertTrue(first.acquire())
        with self.assertRaises(SystemExit) as cm:
            sg.acquire_or_exit(self.path, self.logs.append)
        self.assertEqual(cm.exception.code, 0)

    def test_state_dir_is_not_tmp(self):
        d = str(sg.plugin_state_dir("x"))
        self.assertNotIn("/tmp", d)
        self.assertFalse(d.startswith(tempfile.gettempdir()))


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Consumers(unittest.TestCase):
    """All four daemons use this module, and keep no lock or log under /tmp."""

    def off_tmp(self, p):
        p = str(p)
        self.assertNotIn("/tmp", p)
        self.assertFalse(p.startswith(tempfile.gettempdir()), p)

    def check(self, plugin, entry, log_attr):
        d = PLUGINS / plugin
        sys.path.insert(0, str(d))
        try:
            mod = load(f"consumer_{plugin.replace('-', '_')}", d / entry)
        finally:
            sys.path.remove(str(d))
        self.assertIs(mod.SingletonLock, sg.SingletonLock, plugin)
        self.off_tmp(mod.LOCK_PATH)
        self.assertEqual(Path(mod.LOCK_PATH).parent.parent, sg.STATE_ROOT, plugin)
        self.off_tmp(getattr(mod, log_attr))
        src = (d / entry).read_text()
        self.assertNotIn("LOCK_NB", src, f"{plugin} keeps its own singleton lock code")

    def test_lifeview(self):
        self.check("lifeview-fallback", "lifeview.py", "LOG_PATH")

    def test_claude_name(self):
        self.check("claude-name", "names.py", "LOG_PATH")

    def test_omp_watch(self):
        self.check("omp-watch", "watch.py", "LOG_PATH")

    def test_agent_discord(self):
        self.check("agent-discord", "bot.py", "LOG_FILE")


if __name__ == "__main__":
    unittest.main()
