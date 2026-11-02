#!/usr/bin/env python3
"""Unit tests for lifeview.py's decision logic: python3 test_lifeview.py"""

import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import lifeview as lv


def at(ago_s: float) -> str:
    return datetime.fromtimestamp(time.time() - ago_s).astimezone().isoformat(timespec="seconds")


def agent(status="idle", pane="wX:p1", name="claude-v2-wxp1"):
    return {"pane_id": pane, "name": name, "agent_status": status, "agent": "claude"}


class Decide(unittest.TestCase):
    def d(self, a, entries):
        return lv.decide(a, entries, time.time())

    def test_no_entry_gets_harness_entry_per_herdr_state(self):
        for herdr, state in (("idle", "idle"), ("done", "idle"), ("blocked", "blocked"), ("working", "working")):
            action, e = self.d(agent(herdr), {})
            self.assertEqual(action, "write")
            self.assertEqual((e["state"], e["by"]), (state, "harness"))
            self.assertTrue(e["line"].startswith("harness: "))
            self.assertEqual("ttl_s" in e, state == "working")

    def test_unknown_writes_nothing(self):
        self.assertEqual(self.d(agent("unknown"), {}), ("keep", None))
        self.assertEqual(self.d({"pane_id": "wX:p1"}, {}), ("keep", None))

    def test_fresh_agent_entry_never_overwritten(self):
        e = {"state": "idle", "at": at(30)}
        self.assertEqual(self.d(agent("working"), {"wX:p1": e}), ("keep", None))
        e = {"state": "standby", "at": at(5), "line": "custom line"}
        self.assertEqual(self.d(agent("working"), {"wX:p1": e}), ("keep", None))

    def test_agent_ttl_entry_respected_within_ttl(self):
        e = {"state": "working", "at": at(1000), "ttl_s": 3600}
        self.assertEqual(self.d(agent("idle"), {"wX:p1": e}), ("keep", None))

    def test_stale_but_compatible_agent_entry_kept(self):
        e = {"state": "standby", "at": at(5000), "line": "waiting on verdicts"}
        self.assertEqual(self.d(agent("idle"), {"wX:p1": e}), ("keep", None))

    def test_stale_contradicted_agent_working_replaced(self):
        e = {"state": "working", "at": at(600)}
        action, new = self.d(agent("idle"), {"wX:p1": e})
        self.assertEqual((action, new["state"]), ("write", "idle"))

    def test_stale_settled_agent_word_beats_herdr_working(self):
        # herdr's "working" sticks for hours on omp panes: never overrule idle/standby/blocked
        for state in ("idle", "standby", "blocked"):
            e = {"state": state, "at": at(9000)}
            self.assertEqual(self.d(agent("working"), {"wX:p1": e}), ("keep", None))

    def test_own_entry_kept_while_unchanged_and_refreshed_when_working(self):
        ours = {"state": "idle", "at": at(9000), "by": "harness"}
        self.assertEqual(self.d(agent("idle"), {"wX:p1": ours}), ("keep", None))
        young = {"state": "working", "at": at(30), "by": "harness", "ttl_s": 300}
        self.assertEqual(self.d(agent("working"), {"wX:p1": young}), ("keep", None))
        old = {"state": "working", "at": at(200), "by": "harness", "ttl_s": 300}
        self.assertEqual(self.d(agent("working"), {"wX:p1": old})[0], "write")

    def test_v1_fallback_entries_are_ours_and_migrate(self):
        old = {"state": "idle", "at": at(10), "by": "fallback", "line": "fallback: herdr idle"}
        action, new = self.d(agent("idle"), {"wX:p1": old})
        self.assertEqual((action, new["by"]), ("write", "harness"))

    def test_own_entry_follows_herdr(self):
        ours = {"state": "working", "at": at(10), "by": "harness", "ttl_s": 300}
        action, new = self.d(agent("idle"), {"wX:p1": ours})
        self.assertEqual((action, new["state"]), ("write", "idle"))

    def test_agent_name_entry_drops_our_pane_entry(self):
        entries = {"claude-v2-wxp1": {"state": "idle", "at": at(5)},
                   "wX:p1": {"state": "working", "at": at(5), "by": "harness"}}
        self.assertEqual(self.d(agent("working"), entries), ("drop", None))
        self.assertEqual(self.d(agent("working"), {"claude-v2-wxp1": entries["claude-v2-wxp1"]}), ("keep", None))

    def test_plan_removes_ours_for_dead_panes_only(self):
        entries = {"wX:p9": {"state": "idle", "at": at(5), "by": "harness"},
                   "wX:p8": {"state": "idle", "at": at(5)}}
        self.assertEqual(lv.plan([], entries, set(), time.time()), {"wX:p9": None})


def line(entry):
    return json.dumps(entry).encode()


def ts(ago_s):
    return datetime.fromtimestamp(time.time() - ago_s, timezone.utc).isoformat().replace("+00:00", "Z")


class Transcript(unittest.TestCase):
    def test_classify_claude_and_omp_shapes(self):
        c = lv.classify
        self.assertIsNone(c(line({"type": "system", "timestamp": ts(1)})))
        self.assertEqual(c(line({"type": "user", "message": {"role": "user", "content": "hi"}, "timestamp": ts(1)}))["verdict"], "working")
        self.assertEqual(c(line({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use"}]}}))["verdict"], "working")
        self.assertEqual(c(line({"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}, {"type": "toolCall"}]}}))["verdict"], "working")
        self.assertEqual(c(line({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "thinking"}]}}))["verdict"], "working")
        done = c(line({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Shipped it."}]}, "timestamp": ts(5)}))
        self.assertEqual((done["verdict"], done["text"]), ("answered", "Shipped it."))
        self.assertEqual(c(line({"type": "assistant", "isApiErrorMessage": True, "message": {"role": "assistant", "content": [{"type": "text", "text": "API Error"}]}}))["verdict"], "error")
        self.assertEqual(c(line({"type": "message", "message": {"role": "toolResult"}}))["verdict"], "working")

    def test_scan_tail_skips_bookkeeping_and_partial_lines(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_bytes(b"\n".join([
                line({"type": "user", "message": {"role": "user", "content": "go"}, "timestamp": ts(100)}),
                line({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done: x"}]}, "timestamp": ts(90)}),
                line({"type": "system", "timestamp": ts(89)}),
                line({"type": "last-prompt"}),
            ]) + b"\n" + b'{"type": "user", "mess')        # writer mid-flush
            tail = lv.scan_tail(p)
            self.assertEqual((tail["verdict"], tail["text"]), ("answered", "Done: x"))
            self.assertAlmostEqual(time.time() - tail["at"], 90, delta=3)


def task(state="working", agent_name="claude-v2-wxp1", moved_ago=600, **kw):
    t = {"id": "tk-1", "state": state, "agent": agent_name, "dest": "agent:" + agent_name,
         "history": [{"at": at(moved_ago), "state": state}]}
    t.update(kw)
    return t


def answered(ago=120, text="Implemented the thing; tests pass."):
    return {"verdict": "answered", "at": time.time() - ago, "text": text}


class AutoReady(unittest.TestCase):
    def rc(self, a=None, tasks=None, busy=None, tail=None):
        return lv.ready_check(a or agent("done"), [task()] if tasks is None else tasks, busy or [], tail or answered(), time.time())

    def test_happy_path(self):
        t, why = self.rc()
        self.assertEqual(t["id"], "tk-1", why)

    def test_each_guard_blocks(self):
        self.assertIsNone(self.rc(tasks=[])[0])                                         # nothing to show
        self.assertIsNone(self.rc(tasks=[task(), task(id="tk-2")])[0])                 # ambiguous
        self.assertIsNone(self.rc(tasks=[task(state="reopened")])[0])                  # not an open state
        self.assertIsNone(self.rc(tasks=[task(state="ready")])[0])                     # already green
        for s in ("working", "blocked", "unknown"):
            self.assertIsNone(self.rc(a=agent(s))[0], s)                               # not settled
        self.assertIsNone(self.rc(busy=["claude-v2-wxp2 (working)"])[0])               # coordinator delegated
        self.assertIsNone(self.rc(tail={"verdict": "working", "at": time.time() - 500, "text": ""})[0])
        self.assertIsNone(self.rc(tail={"verdict": "error", "at": time.time() - 500, "text": ""})[0])
        self.assertIsNone(self.rc(tail=answered(ago=10))[0])                           # still settling
        self.assertIsNone(self.rc(tasks=[task(moved_ago=30)], tail=answered(ago=120))[0])  # answer predates the task
        self.assertIsNone(self.rc(tail=answered(text="Should I also update the docs?"))[0])  # a question

    def test_dest_only_task_matches_and_other_agents_do_not(self):
        t = task(agent_name="claude-v2-wxp1")
        del t["agent"]
        self.assertEqual(self.rc(tasks=[t])[0]["id"], "tk-1")
        self.assertIsNone(self.rc(tasks=[task(agent_name="claude-other")])[0])

    def test_task_the_agent_started_is_its_own_call(self):
        t = task(history=[{"at": at(600), "state": "working", "by": "claude-v2-wxp1"}])
        self.assertIsNone(self.rc(tasks=[t])[0])
        old = lv.AUTO_READY_STARTED
        lv.AUTO_READY_STARTED = True
        try:
            self.assertEqual(self.rc(tasks=[t])[0]["id"], "tk-1")
        finally:
            lv.AUTO_READY_STARTED = old
        sent = task(state="sent", history=[{"at": at(600), "state": "sent", "by": "bro"}])
        self.assertEqual(self.rc(tasks=[sent])[0]["id"], "tk-1")

    def test_off_switch(self):
        old = lv.AUTO_READY
        lv.AUTO_READY = False
        try:
            self.assertIsNone(self.rc()[0])
        finally:
            lv.AUTO_READY = old

    def test_summary_is_one_marked_line(self):
        s = lv.summary_of("Line one.\n\nLine   two " + "x" * 400)
        self.assertTrue(s.startswith("auto: Line one. Line two "))
        self.assertLessEqual(len(s), 6 + 240)
        self.assertNotIn("\n", s)


class Icon(unittest.TestCase):
    def test_ranks_like_the_dashboard(self):
        self.assertEqual(lv.icon_state("idle", ["ready"]), "ready")
        self.assertEqual(lv.icon_state("working", ["sent"]), "working")
        self.assertEqual(lv.icon_state("idle", ["sent"]), "queued")
        self.assertEqual(lv.icon_state("blocked", ["working"]), "blocked")
        self.assertEqual(lv.icon_state("idle", []), "idle")
        self.assertEqual(lv.icon_state("standby", []), "idle")


if __name__ == "__main__":
    unittest.main()
