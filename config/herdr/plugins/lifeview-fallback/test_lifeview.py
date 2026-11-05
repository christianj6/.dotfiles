#!/usr/bin/env python3
"""Unit tests for lifeview.py's decision logic: python3 test_lifeview.py"""

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import lifeview as lv


def at(ago_s: float) -> str:
    return datetime.fromtimestamp(time.time() - ago_s).astimezone().isoformat(timespec="seconds")


def agent(status="idle", pane="wX:p1", name="claude-v2-wxp1", project="proj"):
    return {"pane_id": pane, "name": name, "agent_status": status, "agent": "claude", "project": project}


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


def task(state="working", agent_name="claude-v2-wxp1", moved_ago=600, project="proj", target="dev", **kw):
    t = {"id": "tk-1", "state": state, "agent": agent_name, "dest": "agent:" + agent_name,
         "project": project, "target": target,
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

    def test_items_match_on_project_never_agent_or_dest(self):
        # break 1+2: the hub sets neither agent nor dest - an item with neither still matches
        t = task()
        del t["agent"], t["dest"]
        self.assertEqual(self.rc(tasks=[t])[0]["id"], "tk-1")
        # readiness is the project's: an agent field naming someone else does not matter
        self.assertEqual(self.rc(tasks=[task(agent_name="claude-other")])[0]["id"], "tk-1")
        # another project's item never matches, whatever its agent says
        self.assertIsNone(self.rc(tasks=[task(project="other")])[0])
        self.assertIsNone(self.rc(tasks=[task(target="someone")])[0])      # not a hub role

    def test_task_the_agent_started_is_its_own_call(self):
        t = task(history=[{"at": at(600), "state": "working", "by": "claude-v2-wxp1"}])
        self.assertIsNone(self.rc(tasks=[t])[0])
        old = lv.AUTO_READY_STARTED
        lv.AUTO_READY_STARTED = True
        try:
            self.assertEqual(self.rc(tasks=[t])[0]["id"], "tk-1")
        finally:
            lv.AUTO_READY_STARTED = old
        sent = task(state="queued", history=[{"at": at(600), "state": "queued", "by": "bro"}])
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
        tasks = [task(state="queued", moved_ago=600, history=[{"at": at(600), "state": "queued", "by": "bro"}])]
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
        self.assertFalse(lv.pending(a, [task(state="queued")], [], answered(ago=5, text="Which file?"), time.time()))
        self.assertFalse(lv.pending(a, [task(state="queued")], ["omp (working)"], answered(ago=5), time.time()))
        self.assertFalse(lv.pending(agent("blocked"), [task(state="queued")], [], answered(ago=5), time.time()))
        self.assertTrue(lv.pending(a, [task(state="queued")], [], answered(ago=5), time.time()))


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


def turn(calls=2, span=30, said="Refactoring the parser.", key="2026-11-02T12:00:00.000+01:00", prompt="do it", tool="Bash"):
    return {"key": key, "start": time.time() - span, "prompt": prompt, "calls": calls, "said": said, "tool": tool}


class AutoTask(unittest.TestCase):
    SHOWN = {"claude-v2-wxp1"}

    def setUp(self):
        # The machine's lifeview.env may disable auto-task after cut-over; these
        # tests pin the LOGIC, so force it on for their duration.
        self._old_auto = lv.AUTO_TASK
        lv.AUTO_TASK = True

    def tearDown(self):
        lv.AUTO_TASK = self._old_auto

    def chk(self, a=None, tasks=None, t=None, shown=SHOWN, created=frozenset()):
        return lv.autotask_check(a or agent("working"), tasks or [], t or turn(), shown, time.time(), created)

    def test_real_work_session_opens_a_titled_task(self):
        title, why = self.chk()
        self.assertEqual(title, "auto: Refactoring the parser.")
        title, _ = self.chk(t=turn(said="", prompt="Fix the login bug in auth.py please"))
        self.assertEqual(title, "auto: Fix the login bug in auth.py please")
        title, _ = self.chk(t=turn(said="", prompt="", tool="Read"))
        self.assertEqual(title, "auto: running Read")
        title, _ = self.chk(t=turn(said="x" * 500))
        self.assertLessEqual(len(title), 6 + 114)

    def test_threshold_blocks_trivial_turns(self):
        self.assertIsNone(self.chk(t=turn(calls=0, span=600))[0])          # an answer, no tool call
        self.assertIsNone(self.chk(t=turn(calls=1, span=30))[0])           # one quick lookup
        self.assertIsNotNone(self.chk(t=turn(calls=1, span=lv.WORK_MIN_SPAN_S + 5))[0])   # one long tool run
        self.assertIsNotNone(self.chk(t=turn(calls=lv.WORK_MIN_TOOL_CALLS, span=1))[0])

    def test_never_duplicates(self):
        for state in lv.COVERING:                                          # any covering task, handed or auto
            self.assertIsNone(self.chk(tasks=[task(state=state)])[0], state)
        self.assertIsNotNone(self.chk(tasks=[task(state="done")])[0])      # a finished one doesn't cover new work
        t = turn()
        marker = lv.session_marker(agent("working"), t)
        self.assertIsNone(self.chk(t=t, created={marker})[0])              # opened this run
        old = task(state="done", history=[{"at": at(60), "state": "queued", "by": "lifeview-harness", "note": "opened ... " + marker}])
        self.assertIsNone(self.chk(tasks=[old], t=t)[0])                   # opened before a restart, since finished
        self.assertIsNotNone(self.chk(tasks=[old], t=turn(key="2026-11-02T13:00:00.000+01:00"))[0])  # a new turn

    def test_other_gates(self):
        self.assertIsNone(self.chk(a=agent("idle"))[0])
        self.assertIsNone(self.chk(a=agent("blocked"))[0])
        self.assertIsNone(self.chk(shown=None)[0])                         # prescient down
        self.assertIsNone(self.chk(shown={"someone-else"})[0])            # not on the life view
        self.assertIsNone(self.chk(t=turn(key=None))[0])                   # session can't be identified
        old = lv.AUTO_TASK
        lv.AUTO_TASK = False
        try:
            self.assertIsNone(self.chk()[0])
        finally:
            lv.AUTO_TASK = old

    def test_turn_that_just_ended_still_gets_its_task(self):
        done_turn = dict(turn(calls=3, span=40), end=time.time() - 20)
        self.assertIsNotNone(self.chk(a=agent("done"), t=done_turn)[0])
        old_turn = dict(turn(calls=3, span=40), end=time.time() - lv.JUST_DONE_S - 30)
        self.assertIsNone(self.chk(a=agent("done"), t=old_turn)[0])           # no tasks for old turns at daemon start
        short = dict(turn(calls=1, span=200), start=time.time() - 60, end=time.time() - 30)
        self.assertIsNone(self.chk(a=agent("idle"), t=short)[0])              # a finished turn's span is start..end

    def test_task_opened_after_the_answer_still_greens(self):
        key = datetime.fromtimestamp(time.time() - 200).astimezone().isoformat(timespec="milliseconds")
        t = task(state="queued", history=[{"at": at(5), "state": "queued", "by": "lifeview-harness",
                                         "note": f"opened by the lifeview harness ... [lifeview-session wX:p1@{key}]"}])
        got, why = lv.ready_check(agent("done"), [t], [], answered(ago=120), time.time() + 70)
        self.assertEqual(got and got["id"], "tk-1", why)

    def test_harness_created_task_is_auto_ready_eligible(self):
        t = task(state="queued", history=[{"at": at(300), "state": "queued", "by": "lifeview-harness", "note": "opened by the lifeview harness"}])
        got, why = lv.ready_check(agent("done"), [t], [], answered(ago=120), time.time())
        self.assertEqual(got["id"], "tk-1", why)

    def test_scan_turn_counts_back_to_the_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.jsonl"
            p.write_bytes(b"\n".join(line(e) for e in [
                {"type": "user", "message": {"role": "user", "content": "old turn"}, "timestamp": ts(500)},
                {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Old"}]}, "timestamp": ts(490)},
                {"type": "user", "message": {"role": "user", "content": "Refactor the parser"}, "timestamp": ts(100)},
                {"type": "user", "isMeta": True, "message": {"role": "user", "content": "<meta>"}, "timestamp": ts(99)},
                {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "On it."}, {"type": "tool_use", "name": "Read"}]}, "timestamp": ts(90)},
                {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}, "timestamp": ts(80)},
                {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Edit"}, {"type": "tool_use", "name": "Bash"}]}, "timestamp": ts(70)},
            ]) + b"\n")
            t = lv.scan_turn(p)
            self.assertEqual((t["calls"], t["prompt"], t["said"], t["tool"]), (3, "Refactor the parser", "On it.", "Bash"))
            self.assertAlmostEqual(time.time() - t["start"], 100, delta=3)
            self.assertIsNotNone(t["key"])


class Icon(unittest.TestCase):
    def test_ranks_like_the_dashboard(self):
        self.assertEqual(lv.icon_state("idle", ["ready"]), "ready")
        self.assertEqual(lv.icon_state("working", ["sent"]), "working")
        self.assertEqual(lv.icon_state("idle", ["sent"]), "queued")
        self.assertEqual(lv.icon_state("blocked", ["working"]), "blocked")
        self.assertEqual(lv.icon_state("idle", []), "idle")
        self.assertEqual(lv.icon_state("standby", []), "idle")


class TaskHubSwitch(unittest.TestCase):
    """Wave 3 guard: with LIFEVIEW_TASK_HUB unset the plugin must keep talking
    to bro, so an older prescient (no /api/tasks) can never break auto-tasks."""

    def test_default_is_bro(self):
        """The parsed default, independent of this machine's config file (which
        is set to prescient after cut-over): no env, no file -> bro."""
        old_cfg = lv.PLUGIN_CONFIG
        try:
            lv.PLUGIN_CONFIG = Path("/nonexistent/lifeview.env")
            os.environ.pop("LIFEVIEW_TASK_HUB", None)
            self.assertEqual(lv._plugin_env("TASK_HUB", "bro"), "bro")
            os.environ["LIFEVIEW_TASK_HUB"] = "prescient"
            self.assertEqual(lv._plugin_env("TASK_HUB", "bro"), "prescient")
        finally:
            os.environ.pop("LIFEVIEW_TASK_HUB", None)
            lv.PLUGIN_CONFIG = old_cfg

    def test_bro_path_when_hub_unavailable(self):
        old_hub, old_bin, old_avail = lv.TASK_HUB, lv.bro_bin, lv.hub_available
        try:
            lv.TASK_HUB, lv.bro_bin = "prescient", (lambda: None)
            lv.hub_available = lambda: False
            self.assertIsNone(lv.open_task({"pane_id": "wX:p1", "name": "a", "cwd": "/tmp"}, "t", {}))
        finally:
            lv.TASK_HUB, lv.bro_bin, lv.hub_available = old_hub, old_bin, old_avail

    def test_project_name_from_git_toplevel(self):
        # required by the hub; never derived from a dest string
        import subprocess as sp
        with tempfile.TemporaryDirectory() as d:
            sp.run(["git", "init", "-q", d], check=True)
            self.assertEqual(lv.project_name({"cwd": d}), Path(d).name)
        self.assertIsNone(lv.project_name({"cwd": "/nonexistent"}))


class Resolver(unittest.TestCase):
    """Wave 4: prescient publishes {status, why, rank_table_version}; the plugin
    must read it version-gated (never rank against a table it does not know)."""

    def test_known_version_is_used(self):
        self.assertEqual(lv.AG_RANK_VERSION, 2)

    def test_unknown_version_is_flagged_not_trusted(self):
        old = lv.http_json
        try:
            lv.http_json = lambda *a, **k: {"status": "ready", "rank_table_version": 99}
            got = lv.resolver_status("prescient")
            self.assertTrue(got.get("stale_table"), "an unknown table version must be flagged")
        finally:
            lv.http_json = old

    def test_missing_resolver_is_none(self):
        old = lv.http_json
        try:
            lv.http_json = lambda *a, **k: None
            self.assertIsNone(lv.resolver_status("prescient"))
        finally:
            lv.http_json = old


class TaskSystemTurns(unittest.TestCase):
    """The loop rule (2026-11-03): a turn that is itself about the task system
    must never open a task -- it would create a card about the card, which
    nudges the agent, whose next turn does it again."""

    def check(self, turn):
        return lv.task_system_turn(turn)

    def test_coordinator_turns_about_the_hub_are_ignored(self):
        self.assertTrue(self.check({"said": "prescient task list --state queued"}))
        self.assertTrue(self.check({"said": "curl /api/tasks"}))
        self.assertTrue(self.check({"prompt": "clear the queued tasks", "said": "prescient task clear"}))
        self.assertTrue(self.check({"said": "lifeview --explain"}))
        self.assertTrue(self.check({"said": "sqlite3 tasks.sqlite3"}))

    def test_tool_arguments_count_as_the_signal(self):
        """The real looping turn said nothing about the hub -- its Bash ARGUMENTS
        did. That is the signal that has to decide, or the loop survives."""
        self.assertTrue(self.check({"said": "All five cases behave correctly.", "tools": ["Bash"],
                                    "did": '{"command":"prescient task list --state queued"}'}))
        self.assertTrue(self.check({"tools": ["Bash"],
                                    "did": '{"command":"curl -s localhost:8765/api/tasks"}'}))
        self.assertFalse(self.check({"prompt": "fix the parser", "said": "done", "tools": ["Edit"],
                                     "did": '{"path":"src/parser.py"}'}))

    def test_ordinary_project_work_is_not_ignored(self):
        self.assertFalse(self.check({"prompt": "fix the parser", "said": "The parser is fine.", "tools": ["Edit"]}))
        self.assertFalse(self.check({"prompt": "run the tests", "said": "pytest", "tools": ["Bash"]}))
        self.assertFalse(self.check({"tools": ["Bash"]}))          # a tool name alone decides nothing


class CoordinatorExemption(unittest.TestCase):
    """A coordinator's turns ARE coordination; auto-tasking them loops on the
    cards it is creating (2026-11-03). Workhorses keep the automatic green."""

    def test_coordinator_detected_by_target(self):
        self.assertTrue(lv.is_coordinator([{"target": "coordinator"}]))
        self.assertFalse(lv.is_coordinator([{"target": "dev"}]))
        self.assertFalse(lv.is_coordinator([]))

    def test_coordinator_turns_never_open_cards(self):
        title, why = lv.autotask_check(
            {"name": "omp-v34-wdp5", "pane_id": "wD:p5", "agent_status": "working"},
            [{"id": "tk-1", "target": "coordinator", "state": "done"}],
            {"key": "2026-11-03T12:00:00.000+01:00", "start": 0, "calls": 10, "said": "reading the design doc"},
            {"omp-v34-wdp5"}, time.time() + 10 ** 6,
        )
        self.assertIsNone(title)
        self.assertIn("coordinates", why)


def hub_item(state="queued", target="coordinator", project="proj", moved_ago=600, by="owner", iid="tk-h1", **kw):
    """An item as the hub lists it (no agent, no dest), with its event log as history."""
    t = {"id": iid, "text": "x", "project": project, "target": target, "origin": "owner", "state": state,
         "history": [{"at": at(moved_ago), "state": state, "by": by, "note": ""}]}
    t.update(kw)
    return t


class HubPredicate(unittest.TestCase):
    """Break 3, explicitly: the predicate's verdict for EVERY hub state."""
    EXPECT = {  # state: (hub_open, ready_candidate, harness route to ready)
        # candidate == READY_ROUTE is not empty: an item the harness CANNOT drive
        # to ready must not count as "another open item", or it makes every
        # project with one ambiguous and green never happens (created/parked/
        # undelivered had no route yet were candidates - a permanent veto).
        "created": (True, False, None),
        "queued": (True, True, ("start", "ready")),
        "working": (True, True, ("ready",)),
        "ready": (True, False, None),
        "parked": (True, False, None),
        "undelivered": (True, False, None),
        "done": (False, False, None),
    }

    def test_every_hub_state(self):
        rows = ["state        open  candidate  route         ready_check (lone item, settled omp)"]
        for s in lv.HUB_STATES:
            t = hub_item(state=s)
            got_t, why = lv.ready_check(omp(), [t], [], answered(), time.time())
            route = lv.READY_ROUTE.get(s)
            rows.append(f"{s:<12} {str(lv.hub_open(t)):<5} {str(lv.ready_candidate(t)):<10} "
                        f"{'+'.join(route) if route else '-':<13} {'MARK' if got_t else 'no'}: {why}")
            self.assertEqual((lv.hub_open(t), lv.ready_candidate(t), route), self.EXPECT[s], s)
            self.assertEqual(got_t is not None, s in ("queued", "working"), (s, why))
        self.assertEqual(set(lv.HUB_STATES), set(self.EXPECT))
        print("\n" + "\n".join(rows))

    def test_an_unmarkable_item_does_not_veto_the_one_it_can_mark(self):
        """The veto this exists to prevent: 'two candidates is ambiguous' meant a
        parked item sitting beside working work blocked green for ever - the same
        complaint as the original bug, one layer down."""
        working = hub_item(state="working")
        for blocker in ("parked", "created", "undelivered", "ready"):
            tasks = [working, hub_item(id="b", state=blocker)]
            got, why = lv.ready_check(omp(), tasks, [], answered(), time.time())
            self.assertIsNotNone(got, (blocker, why))
            self.assertEqual(got["id"], working["id"], blocker)
        # two items the harness CAN mark stay ambiguous: the agent decides
        got, why = lv.ready_check(omp(), [working, hub_item(id="c", state="working")], [], answered(), time.time())
        self.assertIsNone(got)
        self.assertIn("ambiguous", why)

    def test_dropped_is_done_and_never_a_candidate(self):
        self.assertFalse(lv.ready_candidate(hub_item(state="done", resolution="dropped")))

    def test_bro_display_vocabulary_is_not_the_predicate(self):
        # break 4: BRO_STATES is display-only; bro-local names are not hub states
        for s in ("open", "sent", "reopened", "noted"):
            self.assertFalse(lv.ready_candidate({"state": s}), s)
        # bro's list carries the hub's state beside its own: that one decides
        self.assertTrue(lv.ready_candidate({"state": "sent", "hub_state": "queued"}))


def omp(status="idle", pane="wP:p1", name="omp-v1-wpp1", project="proj"):
    return {"pane_id": pane, "name": name, "agent_status": status, "agent": "omp", "project": project, "cwd": "/w/" + project}


def claude(status="idle", pane="wP:p2", name="claude-v1-wpp2", project="proj"):
    return {"pane_id": pane, "name": name, "agent_status": status, "agent": "claude", "project": project, "cwd": "/w/" + project}


class FakeHub:
    """The hub's /api/tasks write route, with its real rules: by is a role,
    ready only from working, start only from queued."""

    def __init__(self, items):
        self.items, self.calls = {i["id"]: i for i in items}, []

    def __call__(self, url, body=None, timeout=3):
        if body is None:
            return {"items": list(self.items.values())}
        self.calls.append(body)
        it = self.items[body["id"]]
        allowed = {"start": ("queued", "working"), "ready": ("working", "ready")}[body["op"]]
        if body.get("by") not in ("owner", "agent", "harness", "bro") or it["state"] != allowed[0]:
            return None                    # the real hub answers 400; http_json gives None
        it["state"] = allowed[1]
        if body["op"] == "ready":
            it["summary"] = body["summary"]
        return {**it, "item": dict(it)}


class ProjectAutoReady(unittest.TestCase):
    """Acceptance 1, 2, 4, 5: readiness is the project's, settled on its omp."""

    def setUp(self):
        self.saved = (lv.http_json, lv.TASK_HUB, lv.hub_available, lv.transcript_of, lv.scan_tail, lv.AUTO_READY)
        lv.TASK_HUB, lv.hub_available, lv.AUTO_READY = "prescient", (lambda: True), True
        self.dir = tempfile.TemporaryDirectory()
        self.files, self.read = {}, []
        real_scan = self.saved[4]
        lv.transcript_of = lambda a, agents: self.files.get(a["pane_id"])

        def scan(path, *a, **k):
            self.read.append(path)
            return real_scan(path, *a, **k)
        lv.scan_tail = scan

    def tearDown(self):
        (lv.http_json, lv.TASK_HUB, lv.hub_available, lv.transcript_of, lv.scan_tail, lv.AUTO_READY) = self.saved
        self.dir.cleanup()

    def transcript(self, a, text, ago):
        p = Path(self.dir.name) / (a["pane_id"].replace(":", "_") + ".jsonl")
        p.write_bytes(b"\n".join(line(e) for e in [
            {"type": "user", "message": {"role": "user", "content": "go"}, "timestamp": ts(ago + 30)},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}, "timestamp": ts(ago)},
        ]) + b"\n")
        self.files[a["pane_id"]] = p
        return p

    def run_tick(self, agents, items):
        hub = FakeHub(items)
        lv.http_json = hub
        w = lv.World(agents=agents, root_of=lambda cwd: cwd)
        tasks = list(hub.items.values())
        plans = lv.Harness.ready_plans(w, tasks, {})
        lv.Harness().auto_ready(w, tasks, plans)
        return hub, plans

    def test_1_no_claude_coordinator_item_goes_ready_on_the_omp(self):
        o = omp()
        self.transcript(o, "Coordinated it; the fix is merged.", ago=120)
        hub, plans = self.run_tick([o], [hub_item(state="queued")])
        self.assertEqual(hub.items["tk-h1"]["state"], "ready")
        self.assertEqual([(c["op"], c["by"]) for c in hub.calls], [("start", "harness"), ("ready", "harness")])
        self.assertEqual(hub.items["tk-h1"]["summary"], "auto: Coordinated it; the fix is merged.")
        self.assertEqual(plans["proj"]["path"], self.files[o["pane_id"]])

    def test_2_claude_present_its_transcript_is_the_one_read(self):
        o, c = omp(), claude()
        omp_file = self.transcript(o, "Dispatched to claude.", ago=500)       # before the handover: no evidence
        claude_file = self.transcript(c, "Implemented the parser fix; tests pass.", ago=120)
        hub, plans = self.run_tick([o, c], [hub_item(state="working", moved_ago=300)])
        self.assertEqual(hub.items["tk-h1"]["state"], "ready")
        self.assertIs(plans["proj"]["settler"], o)                              # settles on the omp
        self.assertEqual(plans["proj"]["path"], claude_file)                    # WHICH file the tail check read
        self.assertNotEqual(plans["proj"]["path"], omp_file)
        self.assertIn(claude_file, self.read)
        self.assertEqual(hub.items["tk-h1"]["summary"], "auto: Implemented the parser fix; tests pass.")

    def test_2b_claude_present_but_idle_since_handover_reads_the_omp(self):
        o, c = omp(), claude()
        omp_file = self.transcript(o, "Did it myself.", ago=120)
        self.transcript(c, "old work", ago=5000)
        hub, plans = self.run_tick([o, c], [hub_item(state="working", moved_ago=300)])
        self.assertEqual(plans["proj"]["path"], omp_file)
        self.assertEqual(hub.items["tk-h1"]["state"], "ready")

    def test_2c_dev_item_reads_the_claude_and_never_requires_one(self):
        o, c = omp(), claude()
        self.transcript(o, "x", ago=120)
        claude_file = self.transcript(c, "Done.", ago=120)
        _, plans = self.run_tick([o, c], [hub_item(state="working", target="dev")])
        self.assertEqual(plans["proj"]["path"], claude_file)
        o2 = omp(pane="wQ:p1", name="omp-q", project="solo")
        f2 = self.transcript(o2, "Done alone.", ago=120)
        hub, plans = self.run_tick([o2], [hub_item(state="working", target="dev", project="solo")])
        self.assertEqual((plans["solo"]["path"], hub.items["tk-h1"]["state"]), (f2, "ready"))

    def test_guards_still_hold_on_the_project_path(self):
        o, c = omp(), claude(status="working")
        self.transcript(o, "x", ago=120)
        self.transcript(c, "Done.", ago=120)
        hub, _ = self.run_tick([o, c], [hub_item(state="working")])
        self.assertEqual((hub.items["tk-h1"]["state"], hub.calls), ("working", []))   # another agent busy
        o = omp()
        self.transcript(o, "Should I also do the docs?", ago=120)
        hub, _ = self.run_tick([o], [hub_item(state="working")])
        self.assertEqual(hub.calls, [])                                                  # a question
        o = omp()
        self.transcript(o, "Done.", ago=120)
        hub, _ = self.run_tick([o], [hub_item(state="working", by="agent")])
        self.assertEqual(hub.calls, [])                                                  # the agent started it

    def test_4_any_ready_item_makes_the_project_ready_and_is_never_re_marked(self):
        # this plugin's half only; prescient's status() half is routed separately
        others = [s for s in lv.HUB_STATES if s != "ready"]
        for row in ("idle", "working", "blocked", "standby"):
            for s in others:
                items = [hub_item(state="ready", iid="tk-r"), hub_item(state=s, iid="tk-o")]
                self.assertEqual(lv.project_icon(row, "proj", items), "ready", (row, s))
        o = omp()
        self.transcript(o, "Done.", ago=120)
        hub, _ = self.run_tick([o], [hub_item(state="ready")])
        self.assertEqual(hub.calls, [])

    def test_5_history_only_project_is_idle_nothing_open(self):
        items = [hub_item(state="done", resolution="accepted", iid="tk-a"),
                 hub_item(state="done", resolution="dropped", iid="tk-b")]
        self.assertEqual(lv.project_icon("idle", "proj", items), "idle")
        t, why = lv.ready_check(omp(), items, [], answered(), time.time())
        self.assertIsNone(t)
        self.assertIn("nothing open", why)
        o = omp()
        self.transcript(o, "Done.", ago=120)
        hub, plans = self.run_tick([o], items)
        self.assertEqual((plans, hub.calls), ({}, []))
        self.assertEqual(self.read, [])                                                  # no transcript read

class ResolverAttribution(unittest.TestCase):
    """--explain draws ONE icon per agent, but prescient's answer is PER PROJECT.
    Showing a project's answer on every row made an idle omp read "working"
    because its project's Claude was busy (heinzel, 2026-11-03). The rule: only
    the row the resolver names may claim its answer."""

    @staticmethod
    def attributed(name, resolved):
        return bool(resolved and not resolved.get("stale_table")
                    and resolved.get("status") and resolved.get("agent") == name)

    def test_the_named_row_claims_it(self):
        r = {"agent": "omp-x", "status": "working"}
        self.assertTrue(self.attributed("omp-x", r))

    def test_another_row_in_the_same_project_does_not(self):
        r = {"agent": "omp-x", "status": "working"}
        self.assertFalse(self.attributed("claude-y", r))     # the busy project must not paint an idle agent

    def test_a_stale_table_claims_nothing(self):
        self.assertFalse(self.attributed("omp-x", {"agent": "omp-x", "status": "working", "stale_table": True}))

    def test_no_resolver_answer_claims_nothing(self):
        self.assertFalse(self.attributed("omp-x", None))

if __name__ == "__main__":
    unittest.main()
