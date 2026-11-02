#!/usr/bin/env python3
"""Unit tests for lifeview.py's decision logic: python3 test_lifeview.py"""

import time
import unittest
from datetime import datetime

import lifeview as lv


def at(ago_s: float) -> str:
    return datetime.fromtimestamp(time.time() - ago_s).astimezone().isoformat(timespec="seconds")


def agent(status="idle", pane="wX:p1", name="claude-v2-wxp1"):
    return {"pane_id": pane, "name": name, "agent_status": status}


class Decide(unittest.TestCase):
    def d(self, a, entries):
        return lv.decide(a, entries, time.time())

    def test_no_entry_gets_fallback_per_herdr_state(self):
        for herdr, state in (("idle", "idle"), ("done", "idle"), ("blocked", "blocked"), ("working", "working")):
            action, e = self.d(agent(herdr), {})
            self.assertEqual(action, "write")
            self.assertEqual((e["state"], e["by"]), (state, "fallback"))
            self.assertTrue(e["line"].startswith("fallback: "))
            self.assertEqual("ttl_s" in e, state == "working")

    def test_unknown_writes_nothing(self):
        self.assertEqual(self.d(agent("unknown"), {}), ("keep", None))
        self.assertEqual(self.d({"pane_id": "wX:p1"}, {}), ("keep", None))

    def test_fresh_agent_entry_never_overwritten(self):
        e = {"state": "idle", "at": at(30)}
        self.assertEqual(self.d(agent("working"), {"wX:p1": e}), ("keep", None))

    def test_agent_ttl_entry_respected_within_ttl(self):
        e = {"state": "working", "at": at(1000), "ttl_s": 3600}
        self.assertEqual(self.d(agent("idle"), {"wX:p1": e}), ("keep", None))

    def test_stale_but_compatible_agent_entry_kept(self):
        e = {"state": "standby", "at": at(5000), "line": "waiting on verdicts"}
        self.assertEqual(self.d(agent("idle"), {"wX:p1": e}), ("keep", None))

    def test_stale_contradicted_agent_entry_replaced(self):
        e = {"state": "working", "at": at(600)}
        action, new = self.d(agent("idle"), {"wX:p1": e})
        self.assertEqual((action, new["state"]), ("write", "idle"))

    def test_stale_settled_agent_word_beats_herdr_working(self):
        # herdr's "working" sticks for hours on omp panes: never overrule idle/standby/blocked
        for state in ("idle", "standby", "blocked"):
            e = {"state": state, "at": at(9000)}
            self.assertEqual(self.d(agent("working"), {"wX:p1": e}), ("keep", None))

    def test_own_fallback_kept_while_unchanged_and_refreshed_when_working(self):
        ours = {"state": "idle", "at": at(9000), "by": "fallback"}
        self.assertEqual(self.d(agent("idle"), {"wX:p1": ours}), ("keep", None))
        young = {"state": "working", "at": at(30), "by": "fallback", "ttl_s": 300}
        self.assertEqual(self.d(agent("working"), {"wX:p1": young}), ("keep", None))
        old = {"state": "working", "at": at(200), "by": "fallback", "ttl_s": 300}
        self.assertEqual(self.d(agent("working"), {"wX:p1": old})[0], "write")

    def test_own_fallback_follows_herdr(self):
        ours = {"state": "working", "at": at(10), "by": "fallback", "ttl_s": 300}
        action, new = self.d(agent("idle"), {"wX:p1": ours})
        self.assertEqual((action, new["state"]), ("write", "idle"))

    def test_agent_name_entry_drops_our_pane_entry(self):
        entries = {"claude-v2-wxp1": {"state": "idle", "at": at(5)},
                   "wX:p1": {"state": "working", "at": at(5), "by": "fallback"}}
        self.assertEqual(self.d(agent("working"), entries), ("drop", None))
        self.assertEqual(self.d(agent("working"), {"claude-v2-wxp1": entries["claude-v2-wxp1"]}), ("keep", None))

    def test_plan_removes_ours_for_dead_panes_only(self):
        entries = {"wX:p9": {"state": "idle", "at": at(5), "by": "fallback"},
                   "wX:p8": {"state": "idle", "at": at(5)}}
        self.assertEqual(lv.plan([], entries, set(), time.time()), {"wX:p9": None})


if __name__ == "__main__":
    unittest.main()
