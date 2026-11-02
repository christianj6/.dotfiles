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
        ours = {"state": "idle", "at": at(9000), "by": "harness", "line": "harness: herdr idle"}
        self.assertEqual(self.d(agent("idle"), {"wX:p1": ours}), ("keep", None))
        w = "harness: herdr reports working"
        young = {"state": "working", "at": at(30), "by": "harness", "ttl_s": 300, "line": w}
        self.assertEqual(self.d(agent("working"), {"wX:p1": young}), ("keep", None))
        old = {"state": "working", "at": at(200), "by": "harness", "ttl_s": 300, "line": w}
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


class GreyFlash(unittest.TestCase):
    """Invariant: an agent with one open bro task goes working -> ready with
    nothing ranked below working in between; a task-less agent still goes
    idle on the next tick."""

    def ring(self, entry_state, task_state):
        return lv.icon_state(entry_state, [task_state])

    def walk(self, tasks, quiet_points):
        a = agent("done")
        entries, rings = {}, []
        for quiet in quiet_points:
            now = time.time()
            tail = answered(ago=quiet)
            hold = lv.pending(a, tasks, [], tail, now)
            action, e = lv.decide(a, entries, now, hold)
            if action == "write":
                entries["wX:p1"] = e
            t, _ = lv.ready_check(a, tasks, [], tail, now)
            if t:
                t["state"] = "ready"
            rings.append(self.ring(entries["wX:p1"]["state"], tasks[0]["state"] if tasks else "done"))
        return rings, entries

    def test_settle_window_stays_working_until_ready(self):
        tasks = [task(state="sent", moved_ago=600, history=[{"at": at(600), "state": "sent", "by": "bro"}])]
        rings, entries = self.walk(tasks, [2, 15, 30, 45, 58, 61, 75])
        first_ready = rings.index("ready")
        self.assertTrue(all(r == "working" for r in rings[:first_ready]), rings)
        self.assertTrue(all(r == "ready" for r in rings[first_ready:]), rings)
        # once ready, the hold is released: the entry is back to idle (the ring stays green from the task)
        self.assertEqual((entries["wX:p1"]["state"], entries["wX:p1"]["line"]), ("idle", "harness: herdr idle"))

    def test_hold_entry_is_bounded_and_marked(self):
        _, e = lv.decide(agent("done"), {}, time.time(), True)
        self.assertEqual((e["state"], e["line"], e["by"]), ("working", "harness: settling, auto-ready pending", "harness"))
        self.assertLessEqual(e["ttl_s"], lv.SETTLE_S + 3 * lv.POLL_SECONDS)

    def test_no_task_goes_idle_at_once(self):
        a = agent("done")
        self.assertFalse(lv.pending(a, [], [], answered(ago=2), time.time()))
        ours = {"state": "working", "at": at(20), "by": "harness", "ttl_s": 300, "line": "harness: herdr reports working"}
        action, e = lv.decide(a, {"wX:p1": ours}, time.time(), False)
        self.assertEqual((action, e["state"]), ("write", "idle"))

    def test_no_hold_when_it_will_not_go_green(self):
        a = agent("done")
        started = [task(history=[{"at": at(600), "state": "working", "by": "claude-v2-wxp1"}])]
        self.assertFalse(lv.pending(a, started, [], answered(ago=5), time.time()))
        self.assertFalse(lv.pending(a, [task(state="sent")], [], answered(ago=5, text="Which file?"), time.time()))
        self.assertFalse(lv.pending(a, [task(state="sent")], ["omp (working)"], answered(ago=5), time.time()))
        self.assertFalse(lv.pending(agent("blocked"), [task(state="sent")], [], answered(ago=5), time.time()))
        self.assertTrue(lv.pending(a, [task(state="sent")], [], answered(ago=5), time.time()))


def working_tail(ago=5, activity="running bash"):
    return {"verdict": "working", "at": time.time() - ago, "text": "", "activity": activity}


class StaleOverride(unittest.TestCase):
    """A stale agent idle/standby loses to herdr working/blocked only when the
    transcript agrees; the four guards keep the agent's word otherwise."""

    def d(self, herdr, entry, tail, key="wX:p1"):
        return lv.decide(agent(herdr), {key: entry}, time.time(), False, lambda a: tail)

    def test_stale_idle_overridden_when_herdr_and_transcript_agree(self):
        action, e = self.d("working", {"state": "idle", "at": at(5047), "line": "old word"}, working_tail())
        self.assertEqual((action, e["state"], e["by"]), ("write", "working", "harness"))
        self.assertIn("(agent's 84m-old idle overridden)", e["line"])
        self.assertAlmostEqual(e["overrode"]["age_s"], 5047, delta=2)
        self.assertLessEqual(len(e["line"]), 200)

    def test_stale_idle_under_its_name_is_overridden_there(self):
        action, e = self.d("working", {"state": "idle", "at": at(5047)}, working_tail(), key="claude-v2-wxp1")
        self.assertEqual((action, e["state"]), ("write_name", "working"))

    def test_herdr_blocked_overrides_stale_standby(self):
        action, e = self.d("blocked", {"state": "standby", "at": at(900)}, working_tail(activity="running bash"))
        self.assertEqual((action, e["state"]), ("write", "blocked"))
        self.assertTrue(e["line"].startswith("blocked · waiting on an approval prompt"))

    def test_guard_a_fresh_standby_survives(self):
        for ago in (5, 170, 290):           # fresh (<180 s) and within the 300 s staleness window
            self.assertEqual(self.d("working", {"state": "standby", "at": at(ago), "line": "custom"}, working_tail())[0], "keep", ago)
        self.assertEqual(self.d("working", {"state": "idle", "at": at(1000), "ttl_s": 3600}, working_tail())[0], "keep")

    def test_guard_b_agent_blocked_survives_regardless_of_age(self):
        for herdr in ("working", "blocked", "idle"):
            self.assertEqual(self.d(herdr, {"state": "blocked", "at": at(90000)}, working_tail())[0], "keep", herdr)

    def test_guard_c_idle_with_herdr_idle_and_quiet_transcript_not_overridden(self):
        quiet = {"verdict": "answered", "at": time.time() - 4000, "text": "done", "activity": "done"}
        for herdr in ("idle", "done"):
            self.assertEqual(self.d(herdr, {"state": "idle", "at": at(5000)}, quiet)[0], "keep", herdr)
        # herdr working but the transcript has settled: not enough
        self.assertEqual(self.d("working", {"state": "idle", "at": at(5000)}, quiet)[0], "keep")
        settled = {"verdict": "answered", "at": time.time() - 5, "text": "done", "activity": "done"}
        self.assertEqual(self.d("working", {"state": "idle", "at": at(5000)}, settled)[0], "keep")

    def test_guard_d_no_transcript_means_herdr_alone_is_not_enough(self):
        for tail in (None, {"verdict": None, "at": None, "text": "", "activity": None},
                     working_tail(ago=lv.TAIL_RECENT_S + 60)):
            self.assertEqual(self.d("working", {"state": "idle", "at": at(5000)}, tail)[0], "keep", tail)

    def test_override_is_carried_and_logged_once(self):
        _, first = self.d("working", {"state": "idle", "at": at(5047)}, working_tail())
        action, again = lv.decide(agent("working"), {"wX:p1": first}, time.time(), False, lambda a: working_tail(activity="running grep"))
        self.assertEqual(action, "write")                       # the activity changed
        self.assertIn("(agent's 84m-old idle overridden)", again["line"])
        self.assertEqual(again["overrode"], first["overrode"])


class ActivityLine(unittest.TestCase):
    def tail_from(self, entries):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_bytes(b"\n".join(line(e) for e in entries) + b"\n")
            return lv.scan_tail(p)

    def test_last_assistant_text_names_the_activity(self):
        tail = self.tail_from([
            {"type": "user", "message": {"role": "user", "content": "go"}, "timestamp": ts(30)},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Fixed the picker dedupe and\nreran the bench."}, {"type": "tool_use", "name": "Bash"}]}, "timestamp": ts(20)},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}, "timestamp": ts(10)},
        ])
        line_ = lv.activity_line("working", tail, time.time())
        self.assertEqual(line_, "working · Fixed the picker dedupe and reran the bench.")

    def test_tool_call_only_yields_running_tool(self):
        tail = self.tail_from([
            {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "go"}]}, "timestamp": ts(30)},
            {"type": "message", "message": {"role": "assistant", "content": [{"type": "thinking"}, {"type": "toolCall", "name": "bash"}]}, "timestamp": ts(5)},
        ])
        self.assertEqual(lv.activity_line("working", tail, time.time()), "working · running bash")

    def test_an_older_turn_never_shows(self):
        tail = self.tail_from([
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "OLD TURN ANSWER"}]}, "timestamp": ts(300)},
            {"type": "user", "message": {"role": "user", "content": "next task"}, "timestamp": ts(20)},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Read"}]}, "timestamp": ts(10)},
        ])
        self.assertEqual(lv.activity_line("working", tail, time.time()), "working · running Read")

    def test_fallbacks_and_limits(self):
        now = time.time()
        self.assertEqual(lv.activity_line("working", None, now), "working (no recent transcript activity)")
        stale = {"verdict": "working", "at": now - lv.TAIL_RECENT_S - 5, "activity": "x"}
        self.assertEqual(lv.activity_line("working", stale, now), "working (no recent transcript activity)")
        started = {"verdict": "working", "at": now - 3, "activity": None}
        self.assertEqual(lv.activity_line("working", started, now), "working · starting (prompt received)")
        self.assertEqual(lv.activity_line("blocked", None, now), "blocked · waiting on an approval prompt")
        long_ = lv.activity_line("settling", {"at": now, "activity": "y" * 500}, now)
        self.assertTrue(long_.startswith("settling · y"))
        self.assertLessEqual(len(long_), 200)
        self.assertNotIn("\n", long_)

    def test_agent_authored_line_never_rewritten(self):
        e = {"state": "working", "at": at(20), "line": "my own words"}
        self.assertEqual(lv.decide(agent("working"), {"wX:p1": e}, now := time.time(), False,
                                   lambda a: working_tail(activity="something else")), ("keep", None))


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
