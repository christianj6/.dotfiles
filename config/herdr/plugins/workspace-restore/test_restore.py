"""plan() is pure: observed tabs in, steps out. Run: python3 -m unittest test_restore"""
import unittest

import restore


def pane(pid, kind, x=0, agent=None, nvim=None):
    return {"pane_id": pid, "cwd": "/proj", "agent": agent, "kind": kind, "nvim": nvim,
            "rect": {"x": x, "y": 0}}


def tab(*panes, project=True):
    return {"tab_id": "w1:t1", "label": "", "panes": list(panes), "project": project}


IDLE = {"unsaved": 0, "terms": 0}


def actions(tabs, **kw):
    return [(s["target"], s["do"]) for s in restore.plan(tabs, **kw)]


class PlanTest(unittest.TestCase):
    def test_complete_tab_changes_nothing(self):
        t = tab(pane("w1:p1", "agent", agent="omp"), pane("w1:p2", "agent", 90, agent="claude"))
        self.assertEqual(actions([t]), [("w1:p1", None), ("w1:p2", None)])

    def test_restored_tab_two_bare_nvims(self):
        t = tab(pane("w1:p1", "nvim", nvim=IDLE), pane("w1:p2", "nvim", 90, nvim=IDLE))
        self.assertEqual(actions([t]), [("w1:p1", "open_repl"), ("w1:p2", "replace")])

    def test_nvim_with_unsaved_work_or_terminal_is_never_replaced(self):
        for state in ({"unsaved": 1, "terms": 0}, {"unsaved": 0, "terms": 1}, None):
            t = tab(pane("w1:p1", "agent", agent="omp"), pane("w1:p2", "nvim", 90, nvim=state))
            self.assertEqual(actions([t])[1], ("w1:p2", None), state)

    def test_left_nvim_with_terminal_gets_no_ctrl_a(self):
        t = tab(pane("w1:p1", "nvim", nvim={"unsaved": 0, "terms": 1}), pane("w1:p2", "agent", 90, agent="claude"))
        self.assertEqual(actions([t])[0], ("w1:p1", None))

    def test_shell_panes_are_started(self):
        t = tab(pane("w1:p1", "shell"), pane("w1:p2", "shell", 90))
        self.assertEqual(actions([t]), [("w1:p1", "nvim_then_repl"), ("w1:p2", "start_claude")])

    def test_closed_right_pane_stays_closed_unless_asked(self):
        t = tab(pane("w1:p1", "agent", agent="omp"))
        self.assertEqual(actions([t]), [("w1:p1", None), ("w1:t1", None)])
        self.assertEqual(actions([t], create_missing=True)[1], ("w1:t1", "create"))

    def test_work_project_never_gets_a_claude_pane(self):
        for right in ([], [pane("w1:p2", "shell", 90)], [pane("w1:p2", "nvim", 90, nvim=IDLE)]):
            t = dict(tab(pane("w1:p1", "nvim", nvim=IDLE), *right), work=True)
            self.assertEqual([do for _, do in actions([t], create_missing=True)], ["open_repl", None])

    def test_busy_panes_custom_layouts_and_non_projects_are_left_alone(self):
        busy = tab(pane("w1:p1", "busy"), pane("w1:p2", "busy", 90))
        three = tab(pane("w1:p1", "nvim", nvim=IDLE), pane("w1:p2", "nvim", 60, nvim=IDLE), pane("w1:p3", "shell", 120))
        stacked = tab(pane("w1:p1", "nvim", nvim=IDLE), pane("w1:p2", "nvim", 0, nvim=IDLE))
        scratch = tab(pane("w1:p1", "shell"), pane("w1:p2", "shell", 90), project=False)
        for t in (busy, three, stacked, scratch):
            self.assertTrue(all(do is None for _, do in actions([t], create_missing=True)))


if __name__ == "__main__":
    unittest.main()
