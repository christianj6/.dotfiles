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

# Never touch the live daemon's state from a test: the open-outcome file and the
# token's data dir both point into a throwaway folder (no token file in it).
_ISO = tempfile.mkdtemp(prefix="lifeview-test-")
lv.HUB_LAST_PATH = Path(_ISO) / "hub-last.json"
os.environ["PRESCIENT_DATA_DIR"] = _ISO


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

    def test_owner_filed_task_the_agent_started_still_goes_green(self):
        # X1, the incident tk-e9d0ee9c7714: the owner filed it, the agent claimed it with
        # `prescient task start` as its instructions say -> the harness greens it
        hist = [{"at": at(600), "state": "created", "by": "owner"}, {"at": at(600), "state": "queued", "by": "owner"},
                {"at": at(590), "state": "working", "by": "agent"}]
        t, why = self.rc(tasks=[task(origin="owner", history=hist, moved_ago=590)])
        self.assertEqual(t and t["id"], "tk-1", why)
        t, why = self.rc(tasks=[task(origin="bro", history=hist)])                     # the owner's words via bro
        self.assertEqual(t and t["id"], "tk-1", why)

    def test_the_agents_own_work_it_started_is_still_its_call(self):
        hist = [{"at": at(600), "state": "created", "by": "agent"}, {"at": at(590), "state": "working", "by": "agent"}]
        for origin in ("agent", "harness"):                       # harness: auto: cards keep today's refusal
            t, why = self.rc(tasks=[task(origin=origin, history=hist)])
            self.assertIsNone(t, origin)
            self.assertEqual(why, "tk-1 was started by the agent itself: `ready` is its call (LIFEVIEW_AUTO_READY_STARTED=1 overrides)")
        old = lv.AUTO_READY_STARTED
        lv.AUTO_READY_STARTED = True                              # the blunt escape still works
        try:
            self.assertEqual(self.rc(tasks=[task(origin="agent", history=hist)])[0]["id"], "tk-1")
        finally:
            lv.AUTO_READY_STARTED = old

    def test_an_owner_item_nobody_claimed_is_unchanged(self):
        t = task(origin="owner", history=[{"at": at(600), "state": "working", "by": "owner"}])
        self.assertEqual(self.rc(tasks=[t])[0]["id"], "tk-1")
        q = task(state="queued", origin="owner", history=[{"at": at(600), "state": "queued", "by": "owner"}])
        self.assertEqual(self.rc(tasks=[q])[0]["id"], "tk-1")
        # the harness starting an owner item records by=harness, never "agent": not "the agent itself"
        h = task(origin="owner", history=[{"at": at(600), "state": "working", "by": "harness"}])
        self.assertEqual(self.rc(tasks=[h])[0]["id"], "tk-1")
        h2 = task(origin="harness", history=[{"at": at(600), "state": "working", "by": "harness"}])
        self.assertEqual(self.rc(tasks=[h2])[0]["id"], "tk-1")

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
        # no prompt: nothing is attributed, so nothing is opened. It used to
        # become "auto: running Read" - a card for work nobody can be shown to
        # have asked for, which is how machinery became tasks.
        title, why = self.chk(t=turn(said="", prompt="", tool="Read"))
        self.assertIsNone(title)
        self.assertIn("no prompt to attribute", why)
        title, _ = self.chk(t=turn(said="x" * 500))
        self.assertLessEqual(len(title), 6 + 114)

    def unattributed(self):
        """A provenance class that is neither owner nor agent: the threshold
        still applies to it in full (today no such class reaches the gate;
        this pins that the threshold itself is intact)."""
        old = lv.prompt_provenance
        lv.prompt_provenance = lambda turn: "other"
        self.addCleanup(setattr, lv, "prompt_provenance", old)

    def test_threshold_blocks_trivial_turns(self):
        self.assertIsNone(self.chk(t=turn(calls=0, span=600))[0])          # an answer, no tool call
        self.unattributed()
        self.assertIsNone(self.chk(t=turn(calls=1, span=30))[0])           # one quick lookup
        self.assertIsNotNone(self.chk(t=turn(calls=1, span=lv.WORK_MIN_SPAN_S + 5))[0])   # one long tool run
        self.assertIsNotNone(self.chk(t=turn(calls=lv.WORK_MIN_TOOL_CALLS, span=1))[0])

    def test_owner_or_agent_one_call_request_is_work(self):
        """docs/task-autotask-owner-lifecycle.md: the threshold filters incidental
        activity, it does not decide whether the owner asked for something."""
        for prompt in ("Can you check the current git branch in the bro repo and tell me what it is?",
                       "Round 7: docs/specs/x.md - one check"):
            title, why = self.chk(t=turn(calls=1, span=6, prompt=prompt))
            self.assertIsNotNone(title, (prompt, why))
        title, why = self.chk(t=turn(calls=0, span=6, prompt="what branch are we on?"))   # acceptance 5
        self.assertIsNone(title)
        self.assertIn("trivial", why)
        self.assertEqual(lv.WORK_MIN_TOOL_CALLS, 2)                          # not lowered globally

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
        self.unattributed()                                                    # owner/agent one-call turns are work now
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
    cards it is creating (2026-11-03). Workhorses keep the automatic green.

    The judgement is per AGENT and by ROLE. It used to scan the whole list, so one
    coordinator item anywhere marked every agent a coordinator (69 of 100 items
    here) and auto-task was silently dead workspace-wide: nothing the owner said
    was tracked, from bro or from any chat (2026-11-03)."""

    def test_the_omp_is_the_coordinator_and_its_claude_is_not(self):
        self.assertTrue(lv.is_coordinator({"agent": "omp", "project": "proj"}, []))
        self.assertFalse(lv.is_coordinator({"agent": "claude", "project": "proj"}, []))

    def test_another_projects_coordinator_items_do_not_mark_this_agent(self):
        tasks = [{"target": "coordinator", "project": "other"}]
        self.assertFalse(lv.is_coordinator({"agent": "claude", "project": "proj"}, tasks))
        self.assertFalse(lv.is_coordinator({"agent": "claude", "project": "other"}, tasks))

    def test_a_coordinator_item_in_the_same_project_does_not_mark_the_claude(self):
        """The omp shares the project with its Claude, so item history is not
        evidence about a different agent."""
        tasks = [{"target": "coordinator", "project": "proj"}]
        self.assertFalse(lv.is_coordinator({"agent": "claude", "project": "proj"}, tasks))
        self.assertTrue(lv.is_coordinator({"agent": "omp", "project": "proj"}, tasks))

    def test_coordinator_turns_never_open_cards(self):
        title, why = lv.autotask_check(
            {"name": "omp-v34-wdp5", "pane_id": "wD:p5", "agent": "omp", "project": "bro", "agent_status": "working"},
            [{"id": "tk-1", "target": "coordinator", "state": "done", "project": "bro"}],
            {"key": "2026-11-03T12:00:00.000+01:00", "start": 0, "calls": 10, "said": "reading the design doc",
             "prompt": "prescient: task tk-abc is queued for bro's coordinator"},
            {"omp-v34-wdp5"}, time.time() + 10 ** 6,
        )
        self.assertIsNone(title)
        # a hub nudge is machinery now, refused before the coordinator gate -- the
        # gate itself still applies to any non-owner turn that reaches it
        self.assertTrue("never a card" in why or "coordinates" in why, why)

    def test_a_workhorses_work_IS_tracked(self):
        """The owner's rule: things are tracked wherever they came in. A Claude
        doing real work with nothing covering it must open a card."""
        title, why = lv.autotask_check(
            {"name": "claude-v2-w5p1a", "pane_id": "w5:p1A", "agent": "claude", "project": "heinzel",
             "agent_status": "working"},
            [{"id": "tk-1", "target": "coordinator", "state": "done", "project": "heinzel"}],
            {"key": "2026-11-03T17:00:00.000+01:00", "start": 0, "calls": 10, "said": "fixing the z-fighting edge",
             "prompt": "the doorway still z-fights on one edge, fix it"},
            {"claude-v2-w5p1a"}, time.time() + 10 ** 6,
        )
        self.assertIsNotNone(title, why)
        self.assertIn("work session", why)


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

    def __call__(self, url, body=None, timeout=3, **kw):
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
        # X1: was hub_item(state="working", by="agent") - an OWNER item (hub_item's default
        # origin) the agent started - expected to stay unmarked. That is the incident
        # tk-e9d0ee9c7714: the owner's request could never go green. Owner items now go
        # green when claimed (test_owner_filed_task_the_agent_started_still_goes_green);
        # the refusal this line guards is the agent's OWN work, so it is origin="agent".
        hub, _ = self.run_tick([o], [hub_item(state="working", by="agent", origin="agent")])
        self.assertEqual(hub.calls, [])                                                  # the agent started its own work

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

class Provenance(unittest.TestCase):
    """Whose words started this turn (docs/design-task-provenance.md). The owner's
    concern: claude talks to its coordinator through the same chat input he uses,
    so agent comms and machinery were becoming tasks indistinguishable from his."""

    def prov(self, prompt):
        return lv.prompt_provenance({"prompt": prompt})

    def test_machinery_is_never_work(self):
        for p in ("<task-notification> <task-id>x</task-id>",
                  "This session is being continued from a previous conversation that ran out of context.",
                  "[Image: original 3272x864, displayed at 2576x680.]",
                  "<local-command-caveat>",
                  "[Request interrupted by user]"):
            self.assertEqual(self.prov(p), "machinery", p)

    def test_an_agents_own_handoff_is_agent(self):
        for p in ("Round 25: release/docs/ready/round-20261105-balcony-bugs.md - the four bugs",
                  "Round 26, a quick touch-up: release tiny spec",
                  "Spec: the doorway z-fights on one edge",
                  "Discussion, no code: release/docs/ready/trello-material.md"):
            self.assertEqual(self.prov(p), "agent", p)

    def test_human_words_are_the_owners(self):
        for p in ("fix the z-edge, it still flickers",
                  "the doorway still z-fights on one edge, fix it",
                  "that's annoying"):
            self.assertEqual(self.prov(p), "owner", p)

    def test_no_prompt_is_attributable_to_nobody(self):
        self.assertIsNone(self.prov(""))
        self.assertIsNone(lv.prompt_provenance({}))

    def test_machinery_never_opens_a_card(self):
        title, why = lv.autotask_check(
            {"name": "claude-x", "pane_id": "w:p1", "agent": "claude", "project": "proj", "agent_status": "working"},
            [], {"key": "k", "start": 0, "calls": 12, "said": "",
                "prompt": "<task-notification> <task-id>abc</task-id>"},
            {"claude-x"}, time.time() + 10 ** 6)
        self.assertIsNone(title)
        self.assertIn("never a card", why)

    def test_the_transcript_distribution_is_fully_classified(self):
        """The check the coordinator asked for: heinzel's 65 user-role prompts,
        every one in exactly one class, and the counts matching what was measured."""
        prompts = (["Round %d: release/docs/ready/round-2026110%d-x.md" % (i, i % 10) for i in range(19)]
                   + ["<task-notification> <task-id>t%d</task-id>" % i for i in range(16)]
                   + ["[Image: original 3272x864]" for _ in range(11)]
                   + ["a human sentence number %d" % i for i in range(12)]
                   + ["This session is being continued from a previous conversation"] * 6
                   + ["Discussion, no code: release/docs/ready/trello-material.md"])
        self.assertEqual(len(prompts), 65)
        from collections import Counter
        c = Counter(lv.prompt_provenance({"prompt": p}) for p in prompts)
        self.assertEqual(c, Counter({"agent": 20, "machinery": 33, "owner": 12}))
        self.assertEqual(sum(c.values()), 65, "every prompt in exactly one class")

    def test_an_agent_card_never_turns_the_ring_green(self):
        """The owner's attention is the scarce thing: an agent finishing work it
        started is progress, not a verdict request. Without this an agent working
        on its own initiative floods him with 'ready for your verdict' for work he
        never asked for."""
        own = {"id": "a", "project": "p", "target": "coordinator", "state": "ready", "origin": "owner"}
        agt = {"id": "b", "project": "p", "target": "coordinator", "state": "ready", "origin": "agent"}
        self.assertEqual(lv.project_icon("idle", "p", [own]), "ready")
        self.assertEqual(lv.project_icon("idle", "p", [agt]), "working")
        self.assertEqual(lv.project_icon("idle", "p", [own, agt]), "ready")   # his work still wins
        # and the item keeps its real state: only the RING is demoted
        self.assertEqual(lv.hub_state(agt), "ready")


class LifecycleHub:
    """The hub's create/start/ready/list routes and the life view's board, with
    the real rules (create -> queued at once, start only from queued, ready only
    from working, by is a role) and the event log as each item's history."""

    def __init__(self, shown):
        self.items, self.events, self.calls, self.shown = {}, {}, [], shown

    def __call__(self, url, body=None, timeout=3, **kw):
        if url.endswith("/api/agent-board"):
            return {"agents": [{"name": n} for n in self.shown]}
        if body is None:
            return {"items": self.list()}
        self.calls.append(body)
        if body["op"] == "create":
            iid = "tk-c%d" % (len(self.items) + 1)
            self.items[iid] = {"id": iid, "text": body["text"], "project": body["project"],
                               "target": body["target"], "origin": body["origin"], "state": "queued"}
            self.events[iid] = [("created", body["origin"]), ("queued", body["origin"])]
            return {**self.items[iid], "item": dict(self.items[iid])}
        it = self.items[body["id"]]
        frm, to = {"start": ("queued", "working"), "ready": ("working", "ready")}[body["op"]]
        if body.get("by") not in ("owner", "agent", "harness", "bro") or it["state"] != frm:
            return None
        it["state"] = to
        if body["op"] == "ready":
            it["summary"] = body["summary"]
        self.events[it["id"]].append((to, body["by"]))
        return {**it, "item": dict(it)}

    def list(self):
        """A fresh read, as each tick does: no state carried in the dicts."""
        return [dict(i, history=[{"at": at(1), "state": s, "by": b} for s, b in self.events[i["id"]]])
                for i in self.items.values()]


class Clock:
    def __init__(self):
        self.now = time.time()

    def time(self):
        return self.now

    def strftime(self, *a):
        return time.strftime(*a)


class OwnerLifecycle(unittest.TestCase):
    """docs/task-autotask-owner-lifecycle.md: a full lifecycle with nothing
    pre-created in prescient, telling the owner's requests from agent comms."""
    REQUEST = "Can you check the current git branch in the bro repo and tell me what it is? Just run the command."

    def setUp(self):
        saved = {k: getattr(lv, k) for k in ("http_json", "TASK_HUB", "hub_available", "transcript_of",
                                             "AUTO_READY", "AUTO_TASK", "time")}
        self.addCleanup(lambda: [setattr(lv, k, v) for k, v in saved.items()])
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.c, self.o = claude(), omp()
        self.files = {}
        self.hub = LifecycleHub({self.c["name"], self.o["name"]})
        self.clock = Clock()
        lv.http_json, lv.TASK_HUB, lv.hub_available = self.hub, "prescient", (lambda: True)
        lv.AUTO_READY = lv.AUTO_TASK = True
        lv.transcript_of = lambda a, agents: self.files.get(a["pane_id"])
        lv.time = self.clock

    def pane_turn(self, a, prompt, calls=1, answer="On main.", ended_ago=20, commands=("git branch --show-current",)):
        """One turn in the agent's own pane: prompt, `calls` tool calls (Bash, cycling
        through `commands`), answer."""
        # a session header first, as real transcripts have (scan_turn never reads a file's first line)
        entries = [{"type": "session", "timestamp": ts(ended_ago + 60)},
                   {"type": "user", "message": {"role": "user", "content": prompt}, "timestamp": ts(ended_ago + 10)}]
        for i in range(calls):
            entries += [{"type": "assistant", "message": {"role": "assistant", "content": [
                            {"type": "tool_use", "name": "Bash", "input": {"command": commands[i % len(commands)]}}]},
                         "timestamp": ts(ended_ago + 8 - i)},
                        {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "main"}]},
                         "timestamp": ts(ended_ago + 6 - i)}]
        entries.append({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": answer}]},
                        "timestamp": ts(ended_ago)})
        p = Path(self.dir.name) / (a["pane_id"].replace(":", "_") + ".jsonl")
        p.write_bytes(b"\n".join(line(e) for e in entries) + b"\n")
        self.files[a["pane_id"]] = p

    def tick(self, h):
        """Tick's own order (auto-task, then auto-ready) on a fresh hub read."""
        w = lv.World(agents=[self.c, self.o], root_of=lambda cwd: cwd)
        tasks = self.hub.list()
        h.annotate(tasks)
        h.auto_task(w, tasks)
        h.auto_ready(w, tasks, lv.Harness.ready_plans(w, tasks, {}))
        return lv.project_icon("idle", "proj", self.hub.list())

    def test_1_2_owner_one_call_request_runs_the_whole_lifecycle(self):
        self.assertEqual(self.hub.items, {})                     # nothing pre-created in prescient
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.c, self.REQUEST, calls=1)            # a 10 s turn that ended before the tick saw it
        h = lv.Harness()
        rings = [self.tick(h)]                                    # tick 1: the card opens, 20 s after the answer
        self.clock.now += 70                                      # past the settle window
        rings.append(self.tick(h))                                # tick 2: auto-ready
        self.assertEqual([(c["op"], c.get("origin") or c.get("by")) for c in self.hub.calls],
                         [("create", "owner"), ("start", "harness"), ("ready", "harness")])
        (iid, item), = self.hub.items.items()
        self.assertEqual([s for s, _ in self.hub.events[iid]], ["created", "queued", "working", "ready"])
        self.assertEqual(rings, ["queued", "ready"])              # amber, then green
        self.assertEqual(item["origin"], "owner")
        self.assertEqual(item["text"], "auto: " + lv.snippet(self.REQUEST, 114))
        self.assertEqual(item["summary"], "auto: On main.")
        print("\nlifecycle (auto-created only): " + " -> ".join(f"{s} (by {b})" for s, b in self.hub.events[iid])
              + f"; rings per tick: {rings}")

    def test_3_a_coordinators_round_spec_is_an_agent_card_and_never_green(self):
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.c, "Round 7: docs/specs/round-7.md - fix the parser", calls=1, answer="Round 7 done.")
        h = lv.Harness()
        self.tick(h)
        self.clock.now += 70
        ring = self.tick(h)
        (item,) = self.hub.items.values()
        self.assertEqual((item["origin"], item["state"]), ("agent", "ready"))
        self.assertEqual(ring, "working")                         # comms progress, not the owner's verdict

    def test_4_a_task_notification_opens_no_card(self):
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.c, "<task-notification> <task-id>b1</task-id> completed", calls=3)
        self.tick(lv.Harness())
        self.assertEqual((self.hub.items, self.hub.calls), ({}, []))

    def test_5_a_conversational_turn_opens_no_card(self):
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.c, "what branch are we on, roughly?", calls=0, answer="Probably main.")
        self.assertEqual(self.tick(lv.Harness()), "idle")
        self.assertEqual((self.hub.items, self.hub.calls), ({}, []))

    def test_the_owners_own_request_in_an_omp_pane_still_cards(self):
        """The lifecycle must work for the owner wherever he types. Before this,
        his request typed into bro's omp pane produced no card, so the ring went
        amber then straight back to idle."""
        a = {"name": "omp-x", "pane_id": "w:p1", "agent": "omp", "project": "bro", "agent_status": "idle"}
        title, why = lv.autotask_check(
            a, [],
            {"key": "k", "start": time.time() - 20, "calls": 1, "end": time.time() - 14, "said": "",
             "prompt": "Can you check the current git branch in the bro repo and tell me what it is?"},
            {"omp-x"}, time.time())
        self.assertIsNotNone(title, why)
        self.assertIn("work session", why)

    # S1 (2026-11-11): the owner's right-click message to the prescient coordinator was
    # done and never went green -- the work it asked for touched the task system, and
    # the loop guard tested what the work touched instead of who asked.
    S1_MESSAGE = ("[from:owner project:prescient id:prescient-life-view:-message]\n"
                  "From the owner (prescient life view): mark the recipe tweak ready and check the hub row")
    S1_COMMANDS = ("prescient status working 'tweak ready'", "sqlite3 data/tasks.sqlite3 'select id, state from items'",
                   "prescient task ready tk-1 --summary done")

    def test_s1_right_click_message_about_the_task_system_goes_gray_amber_green(self):
        self.assertEqual(self.hub.items, {})                                       # gray: nothing in the hub
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.o, self.S1_MESSAGE, calls=3, answer="Marked ready; the hub row says ready.",
                       commands=self.S1_COMMANDS)
        turn = {"prompt": self.S1_MESSAGE, "tools": ["Bash"], "did": " ".join(self.S1_COMMANDS)}
        self.assertEqual(lv.prompt_provenance(turn), "owner")                     # classified right all along
        self.assertTrue(lv.task_system_turn(turn))                                # the gate that swallowed it
        self.assertTrue(lv.is_coordinator(self.o, []))                            # into the coordinator's pane
        h = lv.Harness()
        rings = [self.tick(h)]
        self.clock.now += 70
        rings.append(self.tick(h))
        (iid, item), = self.hub.items.items()
        self.assertEqual(item["origin"], "owner")
        self.assertEqual([s for s, _ in self.hub.events[iid]], ["created", "queued", "working", "ready"])
        self.assertEqual(rings, ["queued", "ready"])                              # amber, then green
        print("\nS1 right-click message (task-system work, omp): "
              + " -> ".join(f"{s} (by {b})" for s, b in self.hub.events[iid]) + f"; rings per tick: {rings}")

    def test_s1_the_exemption_is_narrow_agent_and_unattributed_task_system_turns_stay_refused(self):
        a = dict(self.c, agent_status="working")
        did = " ".join(self.S1_COMMANDS)
        for prompt in ("Round 7: docs/specs/round-7.md - mark the tweak ready",            # untagged agent shape
                       "From claude-prescient: done, the tweak is ready"):                 # an agent relay
            title, why = lv.autotask_check(a, [], {"key": "k", "start": 0, "calls": 5, "prompt": prompt,
                                                   "tools": ["Bash"], "did": did}, {a["name"]}, time.time() + 10 ** 6)
            self.assertEqual(lv.prompt_provenance({"prompt": prompt}), "agent", prompt)
            self.assertIsNone(title, prompt)
            self.assertIn("about the task system itself", why)
        for prompt in ("[from:harness project:prescient id:prescient]\nmark it ready",       # machinery: refused earlier
                       "prescient: task tk-abc is queued for prescient's coordinator"):
            title, why = lv.autotask_check(a, [], {"key": "k", "start": 0, "calls": 5, "prompt": prompt,
                                                   "tools": ["Bash"], "did": did}, {a["name"]}, time.time() + 10 ** 6)
            self.assertIsNone(title, prompt)
            self.assertIn("never a card", why)
        title, why = lv.autotask_check(a, [], {"key": "k", "start": 0, "calls": 5, "prompt": "", "did": did},
                                       {a["name"]}, time.time() + 10 ** 6)
        self.assertIsNone(title)                                                    # unattributed: nothing
        self.assertIn("no prompt to attribute", why)
        o = dict(self.o, agent_status="working")                                    # the coordinator's own agent turn
        title, why = lv.autotask_check(o, [], {"key": "k", "start": 0, "calls": 5, "prompt": "Round 7: go",
                                               "tools": ["Bash"], "did": "git status"}, {o["name"]}, time.time() + 10 ** 6)
        self.assertIsNone(title)
        self.assertIn("this agent coordinates", why)

    def test_s1_an_owner_turn_without_a_tool_call_is_still_trivial(self):
        o = dict(self.o, agent_status="working")
        title, why = lv.autotask_check(o, [], {"key": "k", "start": time.time() - 5, "calls": 0,
                                               "prompt": self.S1_MESSAGE.replace("mark", "should I mark")},
                                       {o["name"]}, time.time())
        self.assertIsNone(title)
        self.assertIn("trivial so far", why)

    def test_the_loop_stays_closed(self):
        """The reason that gate existed: a hub nudge is machinery, so a card cannot
        nudge the omp whose next turn cards the nudge (2026-11-03)."""
        for prompt in ("prescient: task tk-abc is queued for bro's coordinator",
                       "prescient: 1 tweak sent from the life view",
                       "bro request tr-1: hand over to the bro coordinator"):
            self.assertEqual(lv.prompt_provenance({"prompt": prompt}), "machinery", prompt)


class MessageTags(unittest.TestCase):
    """docs/task-message-tags.md (tk-b32624856c72): the sender writes who it is
    into the text ("[from:<role> project:<p> id:<name>]", put on by omp-peer),
    and the tag is read before every shape rule. Untagged is today's behaviour."""
    BRO_OMP = "[from:coordinator project:bro id:omp-v35-wdp5]"
    OWNER = "[from:owner project:bro id:omp-v35-wdp5]"
    # every shape rule prompt_provenance has, one prompt each
    SHAPES = ("Round 25: release/docs/ready/round-25.md - the four bugs",
              "docs/specs/x.md - fix the parser",
              "<task-notification> <task-id>t1</task-id>",
              "This session is being continued from a previous conversation",
              "prescient: task tk-abc is queued for bro's coordinator",
              "bro request tr-1: hand over",
              "From claude-prescient: done",
              "REPORT round 3 landed",
              "From the owner, via bro: fix it",
              "fix the z-edge, it still flickers")

    setUp, pane_turn, tick = OwnerLifecycle.setUp, OwnerLifecycle.pane_turn, OwnerLifecycle.tick
    REQUEST = OwnerLifecycle.REQUEST

    def prov(self, prompt):
        return lv.prompt_provenance({"prompt": prompt})

    def test_3_owner_tag_beats_every_shape(self):
        self.assertEqual(self.prov(self.OWNER + "\nRound 25: release/docs/ready/round-25.md"), "owner")
        self.assertEqual(self.prov("Round 25: release/docs/ready/round-25.md"), "agent")   # untagged: the shape
        for body in self.SHAPES:
            self.assertEqual(self.prov(self.OWNER + "\n" + body), "owner", body)
            self.assertEqual(self.prov(self.OWNER + " " + body), "owner", body)          # same line works too

    def test_4_harness_tag_is_machinery_and_opens_no_card(self):
        for body in self.SHAPES:
            self.assertEqual(self.prov("[from:harness project:bro id:prescient]\n" + body), "machinery", body)
        title, why = lv.autotask_check(
            {"name": "claude-x", "pane_id": "w:p1", "agent": "claude", "project": "proj", "agent_status": "working"},
            [], {"key": "k", "start": 0, "calls": 12, "said": "",
                 "prompt": "[from:harness project:proj id:prescient]\nCan you check the branch?"},
            {"claude-x"}, time.time() + 10 ** 6)
        self.assertIsNone(title)
        self.assertIn("never a card", why)
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.o, "[from:harness project:proj id:prescient]\nprescient: task tk-1 is queued", calls=3)
        self.tick(lv.Harness())
        self.assertEqual((self.hub.items, self.hub.calls), ({}, []))                   # the loop stays shut

    def test_5_coordinator_worker_and_bro_tags_are_agent(self):
        for role in ("coordinator", "worker", "bro"):
            for body in self.SHAPES:
                if body.startswith(("<task-notification>", "This session")):
                    continue        # (a tag on harness output is not a real case; skip the noise)
                self.assertEqual(self.prov(f"[from:{role} project:dotfiles id:x]\n{body}"), "agent", (role, body))

    def test_only_a_tag_after_harness_wrappers_counts(self):
        # docs/issue-tag-line-two.md: strip the harness's wrappers, then anchor.
        # A tag after real prose is quoted, never honoured -- on line 1 too.
        self.assertEqual(self.prov("Round 25: see [from:owner] below"), "agent")      # after prose: quoted
        self.assertEqual(self.prov("fix it [from:harness]"), "owner")
        self.assertEqual(self.prov("Round 25: go\n[from:owner] quoted"), "agent")      # line 2: untagged
        self.assertEqual(self.prov("[from:alien project:x id:y]\nRound 2: go"), "owner")  # unknown role: untagged, today's rules
        self.assertEqual(self.prov("[from:ownerx]\nfix it"), "owner")                  # \\b: no prefix match
        self.assertEqual(self.prov("  [from:worker project:p id:i] done"), "agent")    # leading space ok
        self.assertEqual(lv.untagged(self.OWNER + "\n  fix it "), "fix it")
        self.assertEqual(lv.untagged("fix it"), "fix it")

    def test_a_coordinator_dispatch_is_agent_not_owner_and_opens_no_card(self):
        """The tk-35a1ddfb2295 / tk-01591d8d2d41 case: the coordinator's dispatch
        to its Claude was prose, so it was recorded origin owner. Tagged, it is agent
        -- and (docs/issue-task-echo.md, the owner's priority #1) agent-to-agent
        comms open NO card at all: the dispatch already is the instruction."""
        dispatch = "Read ~/proj/docs/task-message-tags.md and implement it. Commit locally, do not push."
        self.assertEqual(self.prov(dispatch), "owner")                 # untagged: today's (wrong) answer, unchanged
        tagged = "[from:coordinator project:proj id:omp-x]\n" + dispatch
        self.assertEqual(self.prov(tagged), "agent")                   # provenance stays agent
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.c, tagged, calls=4, answer="Done.")
        h = lv.Harness()
        rings = [self.tick(h)]
        self.clock.now += 70
        rings.append(self.tick(h))
        self.assertEqual((self.hub.items, self.hub.calls), ({}, []))
        self.assertEqual(rings, ["idle", "idle"])

    def test_a_tagged_owner_request_through_bros_omp_runs_the_lifecycle(self):
        """Design acceptance 7: the owner relays by hand into the omp pane
        (omp-peer --from owner); nothing is pre-created in prescient."""
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.o, self.OWNER + "\n" + self.REQUEST, calls=1)
        h = lv.Harness()
        rings = [self.tick(h)]
        self.clock.now += 70
        rings.append(self.tick(h))
        (iid, item), = self.hub.items.items()
        self.assertEqual(item["origin"], "owner")
        self.assertEqual(item["text"], "auto: " + lv.snippet(self.REQUEST, 114))
        self.assertEqual([s for s, _ in self.hub.events[iid]], ["created", "queued", "working", "ready"])
        self.assertEqual(rings, ["queued", "ready"])
        print("\ntagged owner via omp: " + " -> ".join(f"{s} (by {b})" for s, b in self.hub.events[iid])
              + f"; rings per tick: {rings}")


class TaskEcho(unittest.TestCase):
    """docs/issue-task-echo.md: every message arriving in a pane became a hub card.
    Cause 2: coverage was agent-keyed (tasks_of) and hub items carry agent: null,
    so nothing ever covered. Cause 3: agent-to-agent comms were carded at all."""
    setUp, pane_turn, tick = OwnerLifecycle.setUp, OwnerLifecycle.pane_turn, OwnerLifecycle.tick
    REQUEST = OwnerLifecycle.REQUEST

    def hub_item(self, state="working", project="proj", target="coordinator", id="tk-open"):
        # exactly what the hub returns: no agent, no agent:<name> dest
        return {"id": id, "state": state, "agent": None, "dest": None, "project": project,
                "target": target, "origin": "owner", "history": []}

    def chk(self, a, tasks, prompt, calls=3):
        now = time.time()
        return lv.autotask_check(dict(a, agent_status="working"), tasks,
                                 {"key": "k" + prompt[:6], "start": now - 60, "calls": calls, "said": "", "prompt": prompt},
                                 {a["name"]}, now)

    def test_2_an_open_project_item_covers_the_workers_next_turn(self):
        item = self.hub_item()
        self.assertEqual(lv.tasks_of(self.c, [item]), [])                 # the old key: can never match
        self.assertEqual(lv.covering_items(self.c, [item]), [item])       # the new key: project
        title, why = self.chk(self.c, [item], "Both landed, 998 tests OK")
        self.assertIsNone(title)
        self.assertEqual(why, "covered by tk-open (working)")
        for target in ("coordinator", "dev"):                             # whatever its role target
            for state in ("created", "queued", "working"):
                self.assertIsNone(self.chk(self.c, [self.hub_item(state, target=target)], "next")[0], (target, state))

    def test_coverage_stays_inside_the_project_and_in_progress(self):
        for item in (self.hub_item(project="other"),                      # another project's work
                     self.hub_item(state="done"),
                     self.hub_item(state="parked"),
                     self.hub_item(state="ready")):                       # awaiting the owner's verdict
            self.assertEqual(lv.covering_items(self.c, [item]), [], item)
            self.assertIsNotNone(self.chk(self.c, [item], self.REQUEST)[0], item)

    def test_bro_list_items_still_cover_by_agent(self):
        bro = {"id": "tk-b", "state": "sent", "agent": self.c["name"], "project": None, "target": None}
        self.assertEqual(lv.covering_items(self.c, [bro]), [bro])

    def test_2_the_echo_is_impossible_end_to_end(self):
        """Owner request -> card; while it is open, more turns in the worker's
        pane (a report, another instruction) open nothing: one card in total."""
        self.c["agent_status"] = self.o["agent_status"] = "working"
        self.pane_turn(self.c, self.REQUEST, calls=2, ended_ago=0)
        h = lv.Harness()
        self.tick(h)
        self.assertEqual(len(self.hub.items), 1)
        for i, prompt in enumerate(("Both landed, 998 tests OK", "docs/x.report.md - done", "and the follow-up")):
            self.pane_turn(self.c, prompt, calls=3, ended_ago=30 - 10 * i)   # each its own session key
            self.clock.now += 15
            self.tick(h)
        self.assertEqual(len(self.hub.items), 1, [i["text"] for i in self.hub.items.values()])
        self.assertEqual([c["op"] for c in self.hub.calls], ["create"])

    def test_3_tagged_comms_open_no_card_in_either_direction(self):
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        self.pane_turn(self.c, "[from:coordinator project:proj id:omp-x]\nRead docs/task-x.md and implement it", calls=5)
        self.pane_turn(self.o, "[from:worker project:proj id:claude-x]\ndocs/task-x.report.md - done, 95 tests OK", calls=2)
        self.tick(lv.Harness())
        self.assertEqual((self.hub.items, self.hub.calls), ({}, []))
        title, why = self.chk(self.c, [], "[from:worker project:proj id:claude-y]\nreview this")
        self.assertIsNone(title)
        self.assertIn("comms, never a card", why)

    def test_4_owner_requests_still_card_and_complete_one_after_another(self):
        """The editorial guard: an owner request in a pane creates ONE card and
        completes -- also the second one, while the first sits ready for review."""
        self.c["agent_status"] = self.o["agent_status"] = "idle"
        h = lv.Harness()
        for n, request in enumerate((self.REQUEST, "[from:owner project:proj id:omp-x]\nNow check the tags too, please.")):
            self.pane_turn(self.c, request, calls=1, ended_ago=20 - 15 * n)   # two turns, two session keys
            self.tick(h)
            self.clock.now += 70
            self.assertEqual(self.tick(h), "ready")
            self.assertEqual(len(self.hub.items), n + 1)
        self.assertEqual(sorted((i["origin"], i["state"]) for i in self.hub.items.values()),
                         [("owner", "ready"), ("owner", "ready")])

    def test_5_untagged_shapes_are_unchanged(self):
        for prompt, origin in (("Round 25: release/docs/ready/r.md", "agent"), ("fix it", "owner"),
                               ("prescient: task tk-1 is queued", "machinery"),
                               ("From claude-prescient: done", "agent")):
            self.assertEqual(lv.prompt_provenance({"prompt": prompt}), origin, prompt)
        self.assertIsNotNone(self.chk(self.c, [], "Round 25: release/docs/ready/r.md - go")[0])  # still a card


class TagNotAtStart(unittest.TestCase):
    """docs/issue-tag-not-at-start.md: the harness can frame our text
    ('<pasted_content id="…"> ', 'auto: '), so the tag is not at offset 0. The
    anchored match missed it and the message fell through to owner (the echo's
    third cause, tk-695297b6575d)."""
    PASTED = '<pasted_content id="f3ce"> [from:coordinator project:prescient id:omp-v35-wdp7] The message'

    def setUp(self):
        lv._unparsed_seen.clear()
        self.events = []
        old = lv.log
        lv.log = lambda msg: self.events.append(msg)
        self.addCleanup(setattr, lv, "log", old)

    def prov(self, prompt):
        return lv.prompt_provenance({"prompt": prompt})

    def chk(self, prompt):
        a = {"name": "claude-x", "pane_id": "w:p1", "agent": "claude", "project": "proj", "agent_status": "working"}
        now = time.time()
        return lv.autotask_check(a, [], {"key": "k", "start": now - 60, "calls": 3, "said": "", "prompt": prompt},
                                 {"claude-x"}, now)

    def unparsed(self):
        return [e for e in self.events if e.startswith("event tag_unparsed ")]

    def test_1_a_pasted_wrapper_before_the_tag(self):
        self.assertEqual(self.prov(self.PASTED), "agent")
        for role in ("coordinator", "worker"):
            title, why = self.chk(f'<pasted_content id="x"> [from:{role} project:p id:a] text')
            self.assertIsNone(title)
            self.assertIn("comms, never a card", why)
        self.assertEqual(self.unparsed(), [])                       # it parsed: no event

    def test_2_an_auto_prefix_before_an_owner_tag(self):
        self.assertEqual(self.prov("auto: [from:owner project:p id:a] text"), "owner")
        self.assertEqual(self.prov("auto: [from:owner project:p id:a] Round 25: docs/x.md"), "owner")

    def test_3_a_plain_tag_at_the_start_still_works(self):
        for role, origin in (("owner", "owner"), ("coordinator", "agent"), ("worker", "agent"),
                             ("bro", "agent"), ("harness", "machinery")):
            self.assertEqual(self.prov(f"[from:{role} project:p id:a]\nRound 25: x"), origin, role)

    def test_4_a_tag_only_in_line_two_or_beyond_is_untagged(self):
        quoted = "here is the log you asked for:\n[from:coordinator project:p id:a] Both landed"
        self.assertEqual(self.prov(quoted), "owner")                 # today's untagged answer, not the quoted agent
        self.assertEqual(self.prov("Round 3: docs/x.md\n\n[from:owner project:p id:a] quoted"), "agent")
        self.assertEqual(self.prov("prescient: task tk-1 queued\n[from:owner] x"), "machinery")
        self.assertIsNotNone(self.chk(quoted)[0])                    # the owner's request still cards
        self.assertEqual(lv.untagged(quoted), quoted)                # nothing stripped
        # after prose on the SAME line is quoted too (docs/issue-tag-line-two.md)
        self.assertEqual(self.prov("the log says [from:worker project:p id:a] done"), "owner")

    def test_first_match_wins(self):
        self.assertEqual(self.prov("[from:harness project:p id:a] [from:owner project:p id:b] x"), "machinery")
        self.assertEqual(self.prov("[from:owner project:p id:b] [from:harness project:p id:a] x"), "owner")

    def test_5_untagged_strips_the_tag_wherever_it_is(self):
        self.assertEqual(lv.untagged(self.PASTED), "The message")
        self.assertEqual(lv.untagged(self.PASTED + ' </pasted_content id="f3ce">'), "The message")
        self.assertEqual(lv.untagged("auto: [from:owner project:p id:a] text"), "text")
        self.assertEqual(lv.untagged("[from:owner project:p id:a]\nfix it"), "fix it")
        q = "Round 25: see [from:owner project:p id:a] below"
        self.assertEqual(lv.untagged(q), q)                         # quoted, not a tag: left alone
        # the card's text carries neither wrapper nor tag
        self.assertEqual(lv.snippet(lv.untagged(self.PASTED), 114), "The message")

    def test_6_a_contained_tag_that_does_not_parse_emits_tag_unparsed(self):
        for prompt, where in (("[from:alien project:p id:a] hi", "at the start"),
                              ("[from:owner project:p id:a hi (no closing bracket)", "at the start"),
                              ("look:\n[from:worker project:p id:a] quoted", "quoted tag, not honoured")):
            self.events.clear()
            lv._unparsed_seen.clear()
            self.prov(prompt)
            (ev,) = self.unparsed()
            body = json.loads(ev[len("event tag_unparsed "):])
            self.assertIn(where, body["where"])
            self.assertEqual(body["head"], prompt[:120])
        self.events.clear()
        for _ in range(5):                                           # every tick classifies again: one event, not five
            self.prov("[from:alien] repeated")
        self.assertEqual(len(self.unparsed()), 1)
        self.events.clear()
        for prompt in ("fix it", self.PASTED, "[from:owner project:p id:a] x"):
            self.prov(prompt)
        self.assertEqual(self.unparsed(), [])                        # no "[from:" or it parsed: silent

    def test_7_untagged_cases_unchanged(self):
        for prompt, origin in (("Round 25: release/docs/ready/r.md", "agent"), ("fix it", "owner"),
                               ("<task-notification> <task-id>t</task-id>", "machinery"),
                               ("prescient: task tk-1 is queued", "machinery"),
                               ("From claude-prescient: done", "agent"), ("From the owner, via bro: x", "owner")):
            self.assertEqual(self.prov(prompt), origin, prompt)
        self.assertEqual(self.unparsed(), [])


class TagAfterWrapper(unittest.TestCase):
    """docs/issue-tag-line-two.md, the echo's fourth cause: prescient's pane gets
    '<pasted_content id="…">' on its OWN line, so the tag sat on line 2 and the
    first-line search refused it. Rule now: strip harness wrappers, then anchor."""
    T = "[from:coordinator project:prescient id:omp-v35-wdp7]"

    setUp, prov, chk, unparsed = (TagNotAtStart.setUp, TagNotAtStart.prov,
                                  TagNotAtStart.chk, TagNotAtStart.unparsed)

    def test_1_wrapper_on_the_same_line(self):
        p = f'<pasted_content id="x"> {self.T} text'
        self.assertEqual(self.prov(p), "agent")
        self.assertEqual(lv.untagged(p), "text")

    def test_2_wrapper_on_its_own_line(self):
        p = f'<pasted_content id="f3ce">\n{self.T} Real owner task'     # the reproduced prompt
        self.assertEqual(self.prov(p), "agent")
        self.assertEqual(lv.untagged(p), "Real owner task")
        self.assertIsNone(self.chk(p)[0])                                # comms: no card
        self.assertIsNone(self.chk(p.replace("coordinator", "worker", 1))[0])
        self.assertEqual(lv.untagged(p + '\n</pasted_content id="f3ce">'), "Real owner task")
        self.assertEqual(self.unparsed(), [])

    def test_3_auto_prefix_then_owner(self):
        self.assertEqual(self.prov("auto: [from:owner project:p id:a] text"), "owner")
        self.assertEqual(lv.untagged("auto: [from:owner project:p id:a] text"), "text")

    def test_4_a_tag_after_real_prose_is_not_honoured_and_logs(self):
        for p in ("here is a log:\n[from:harness project:p id:a] x",
                  "here is a log: [from:harness project:p id:a] x",
                  '<pasted_content id="x">\nhere is a log:\n[from:coordinator project:p id:a] x'):
            self.events.clear()
            lv._unparsed_seen.clear()
            self.assertEqual(self.prov(p), "owner", p)                  # today's untagged answer
            self.assertIsNotNone(self.chk(p)[0], p)                     # the owner's message still cards
            (ev,) = self.unparsed()
            self.assertIn("quoted tag, not honoured", ev)

    def test_5_several_wrappers_in_a_row(self):
        for p in (f'<pasted_content id="a">\n<pasted_content id="b">\n{self.T} x',
                  f'auto: <pasted_content id="a">\n{self.T} x',
                  f'  <PASTED_CONTENT id="a"> auto:\n\n {self.T} x'):
            self.assertEqual(self.prov(p), "agent", p)
            self.assertEqual(lv.untagged(p), "x", p)

    def test_6_a_plain_tag_at_the_start(self):
        self.assertEqual(self.prov("[from:owner project:p id:a]\nRound 25: x"), "owner")
        self.assertEqual(self.prov("[from:harness project:p id:a] fix it"), "machinery")

    def test_7_untagged_cases_unchanged(self):
        TagNotAtStart.test_7_untagged_cases_unchanged(self)
        # a wrapper alone is not a tag: an untagged wrapped message is today's answer
        self.assertEqual(self.prov('<pasted_content id="x">\nfix the parser'), "owner")
        self.assertEqual(lv.untagged('<pasted_content id="x">\nfix it'), '<pasted_content id="x">\nfix it')


class NudgeLiterals(unittest.TestCase):
    """docs/task-nudge-loop-verify.md: the LITERAL user-role strings prescient's
    deliveries leave in a transcript (copied from real omp and claude transcripts,
    every distinct shape found) must stay machinery -- plain, tagged, and behind
    harness framing -- and never open a card. The reverse: an owner line that only
    starts with "prescient:" is not silently machinery."""
    NUDGE = "prescient: task tk-521d85e1842a is queued for dotfiles's coordinator - `prescient task list --mine` has it."
    NUDGE_DEV = "prescient: task tk-0f3a9c2e7b14 is queued for bro's dev - `prescient task list --mine` has it."
    TWEAK = ("prescient: 1 tweak sent from the life view - run `.venv/bin/prescient tweak list`, "
             "then follow the tweak routine in AGENTS.md.")
    TWEAKS = ("prescient: 2 tweaks sent from the life view - run `.venv/bin/prescient tweak list`, "
              "then follow the tweak routine in AGENTS.md.")
    NUDGE_TAG = "[from:harness project:prescient id:prescient-task-nudge]\n"
    TWEAK_TAG = "[from:harness project:prescient id:prescient-tweak-doorbell]\n"
    LITERALS = (NUDGE, NUDGE_DEV, TWEAK, TWEAKS, NUDGE_TAG + NUDGE, TWEAK_TAG + TWEAK,
                (TWEAK_TAG + TWEAK) * 3)      # the doorbell delivered three times into one entry
    FRAMINGS = ('<pasted_content id="x">', '<pasted_content id="x"> ', '<pasted_content id="x">\n',
                "auto: ", 'auto: <pasted_content id="x"> ', NUDGE_TAG)

    def setUp(self):
        lv._unparsed_seen.clear()
        self.events = []
        old = lv.log
        lv.log = lambda msg: self.events.append(msg)
        self.addCleanup(setattr, lv, "log", old)

    def prov(self, prompt):
        return lv.prompt_provenance({"prompt": prompt})

    def chk(self, prompt, coordinator=False):
        a = {"name": "omp-x" if coordinator else "claude-x", "pane_id": "w:p1",
             "agent": "omp" if coordinator else "claude", "project": "proj", "agent_status": "working"}
        now = time.time()
        return lv.autotask_check(a, [], {"key": "k", "start": now - 60, "calls": 3, "said": "", "prompt": prompt},
                                 {a["name"]}, now)

    def unrecognized(self):
        return [e for e in self.events if e.startswith("event machinery_unrecognized ")]

    def test_literals_are_machinery_and_never_card(self):
        for lit in self.LITERALS:
            with self.subTest(lit=lit[:60]):
                self.assertEqual(self.prov(lit), "machinery")
                for coord in (False, True):
                    title, why = self.chk(lit, coord)
                    self.assertIsNone(title, why)
        self.assertEqual(self.unrecognized(), [])     # known shapes are not reported

    def test_literals_behind_framing_are_machinery(self):
        for lit in (self.NUDGE, self.TWEAK):
            for fr in self.FRAMINGS:
                for close in ("", '</pasted_content id="x">') if "pasted" in fr else ("",):
                    p = fr + lit + close
                    with self.subTest(p=p[:80]):
                        self.assertEqual(self.prov(p), "machinery")
                        self.assertIsNone(self.chk(p)[0])

    def test_a_paste_with_the_senders_own_words_after_it_is_theirs(self):
        p = f'<pasted_content id="x">{self.NUDGE}</pasted_content id="x"> why does this keep coming back?'
        self.assertEqual(self.prov(p), "owner")

    def test_reverse_owner_text_starting_prescient_is_not_silently_machinery(self):
        # Explicitly the owner's: owner, whatever follows.
        self.assertEqual(self.prov("[from:owner project:dotfiles id:owner]\nprescient: why did bro show twice?"), "owner")
        self.assertEqual(self.prov("From the owner (prescient): prescient: why did bro show twice?"), "owner")
        # Unmarked: still machinery (the "prescient: " rule is not weakened) but REPORTED, once.
        for _ in range(3):
            self.assertEqual(self.prov("prescient: why did the life view show bro twice?"), "machinery")
        self.assertEqual(len(self.unrecognized()), 1)
        self.assertIn("tag it [from:owner]", self.unrecognized()[0])

    def test_a_delivery_spliced_into_the_owners_typing_is_the_owners(self):
        # One real entry: the doorbell landed while the owner was typing.
        p = "i had to ma" + self.TWEAK + "nu"
        self.assertEqual(self.prov(p), "owner")



class HubWriteToken(unittest.TestCase):
    """docs/task-plugin-write-token.md: every hub write carries the launch token,
    read per call; a refusal is logged once; the token never reaches a log line."""

    TOKEN = "tok-" + "x" * 40

    def setUp(self):
        import http.server
        import threading
        test = self
        self.seen, self.logs = [], []

        class Hub(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                tok = self.headers.get("X-Prescient-Token")
                test.seen.append((body, tok))
                if tok != test.TOKEN:      # prescient's strict gate: its exact refusal text
                    code, out = 403, {"error": "a write needs this launch's token (X-Prescient-Token; data/.server-token has it)"}
                else:
                    code, out = 200, {"item": {"id": "it-test1", "state": "queued", **body}}
                raw = json.dumps(out).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.srv = http.server.HTTPServer(("127.0.0.1", 0), Hub)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.data = tempfile.TemporaryDirectory()
        port = self.srv.server_address[1]
        self.tokfile = Path(self.data.name) / f".server-token-{port}"     # non-default port: the -<port> file
        saved = (lv.HUB_URL, lv.log, os.environ.get("PRESCIENT_DATA_DIR"), dict(lv._refusals_seen))
        lv.HUB_URL = f"http://127.0.0.1:{port}"
        lv.log = self.logs.append
        os.environ["PRESCIENT_DATA_DIR"] = self.data.name
        lv._refusals_seen.clear()

        def restore():
            lv.HUB_URL, lv.log = saved[0], saved[1]
            os.environ["PRESCIENT_DATA_DIR"] = saved[2]
            lv._refusals_seen.clear()
            lv._refusals_seen.update(saved[3])
            self.srv.shutdown()
            self.srv.server_close()
            self.data.cleanup()
        self.addCleanup(restore)

    def create(self):
        a = agent("working", pane="wD:pA", name="claude-v2-wdpa", project="dotfiles")
        turn = {"prompt": "[from:owner project:dotfiles] fix the plugin's write token", "key": "k1", "start": 1.0}
        return lv.hub_open_task(a, "auto: fix the plugin's write token", turn)

    def test_write_with_the_token_succeeds(self):
        self.tokfile.write_text(self.TOKEN + "\n")
        self.assertEqual(self.create(), "it-test1")
        body, tok = self.seen[-1]
        self.assertEqual(tok, self.TOKEN)
        self.assertEqual((body["op"], body["project"], body["target"], body["origin"]),
                         ("create", "dotfiles", "coordinator", "owner"))
        self.assertEqual(lv.last_open("claude-v2-wdpa")["outcome"], "ok")
        self.assertEqual(self.logs, [])

    def test_token_is_read_per_call_not_cached(self):
        self.tokfile.write_text("stale-token\n")      # a previous launch's token
        self.assertIsNone(self.create())
        self.tokfile.write_text(self.TOKEN + "\n")    # the hub restarted: a new file
        self.assertEqual(self.create(), "it-test1")

    def test_wrong_token_is_refused_and_logged_once(self):
        self.tokfile.write_text("wrong-token\n")
        self.assertIsNone(self.create())
        self.assertIsNone(self.create())               # second identical refusal: no second log line
        refused = [l for l in self.logs if "refused" in l]
        self.assertEqual(len(refused), 1, self.logs)
        self.assertIn("403", refused[0])
        self.assertIn("needs this launch's token", refused[0])
        lo = lv.last_open("claude-v2-wdpa")
        self.assertEqual(lo["outcome"], "refused")
        self.assertIn("403", lo["detail"])
        for l in self.logs + [json.dumps(lo)]:
            self.assertNotIn("wrong-token", l)
            self.assertNotIn(self.TOKEN, l)

    def test_write_without_a_token_file_reports_the_refusal(self):
        self.assertIsNone(self.create())               # no token file at all
        self.assertIsNone(self.seen[-1][1])            # nothing invented: no header sent
        self.assertEqual(len(self.logs), 1, self.logs)
        self.assertIn("403", self.logs[0])
        self.assertIn("unreadable", self.logs[0])      # distinct and actionable: names the missing file
        self.assertIn(self.tokfile.name, self.logs[0])

    def test_unset_data_dir_says_how_to_set_it(self):
        os.environ.pop("PRESCIENT_DATA_DIR")
        saved = lv.PLUGIN_CONFIG
        lv.PLUGIN_CONFIG = Path(self.data.name) / "absent.env"
        self.addCleanup(setattr, lv, "PLUGIN_CONFIG", saved)
        self.assertIsNone(self.create())
        self.assertIn("PRESCIENT_DATA_DIR is not set", self.logs[0])

    def test_no_hub_write_bypasses_the_helper(self):
        src = Path(lv.__file__).read_text()
        import re as _re
        posts = _re.findall(r"http_json\(HUB_URL \+ \"/api/tasks\", [^t)]", src)
        self.assertEqual(len(posts), 1, posts)        # the one inside hub_write()


if __name__ == "__main__":
    unittest.main()
