#!/usr/bin/env python3
"""Tests for names.py's naming rules. Run with `python3 test_names.py`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import names  # noqa: E402


def agent(name=None, status="idle", kind="claude", pane="wD:pA"):
    return {"agent": kind, "agent_status": status, "name": name, "pane_id": pane}


def test_version():
    assert names.parse_major("2.1.316 (Claude Code)\n") == "2"
    assert names.parse_major("10.0.1") == "10"
    assert names.parse_major("") is None
    assert names.parse_major("not a version") is None


def test_target():
    assert names.pane_suffix("wD:pA") == "wdpa"
    assert names.target_name("wD:p9", "2") == "claude-v2-wdp9"
    assert names.target_name("w5:p1A", None) == "claude-w5p1a"


def test_rename_needed():
    assert names.rename_needed(agent(), "2") == "claude-v2-wdpa"
    assert names.rename_needed(agent("claude-dotfiles"), "2") == "claude-v2-wdpa"
    assert names.rename_needed(agent("claude-v1-wdpa"), "2") == "claude-v2-wdpa"
    assert names.rename_needed(agent(status="unknown"), "2") == "claude-v2-wdpa"
    assert names.rename_needed(agent("claude-wdpa"), "2") == "claude-v2-wdpa"


def test_left_alone():
    assert names.rename_needed(agent("claude-v2-wdpa"), "2") is None
    assert names.rename_needed(agent("claude-wdpa"), None) is None
    assert names.rename_needed(agent(status="working"), "2") is None
    assert names.rename_needed(agent(status="blocked"), "2") is None
    assert names.rename_needed(agent(kind="omp"), "2") is None


def test_claude_env_has_no_herdr_vars():
    names.os.environ["HERDR_PANE_ID"] = "wD:pA"
    assert not [k for k in names.claude_env() if k.startswith("HERDR_")]


# --- config-version marker (docs/task-claude-pane-version.md) -----------------

import os, subprocess, tempfile  # noqa: E402

HOOK = Path(__file__).resolve().parents[4] / "config/claude/hooks/claude-config-version.sh"


def test_marker_names_the_pane_by_config_version():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "4242").write_text("36\n")
        v = names.marker_version(4242, Path(d))
        assert v == "36"
        assert names.target_name("wD:pA", "2", v) == "claude-v36-wdpa"         # config beats the CLI major
        assert names.rename_needed(agent("claude-v2-wdpa"), "2", v) == "claude-v36-wdpa"
        assert names.rename_needed(agent("claude-v36-wdpa"), "2", v) is None
        (Path(d) / "4243").write_text("35")                                     # a stale pane keeps its number
        assert names.rename_needed(agent("claude-v36-wdpa"), "2", names.marker_version(4243, Path(d))) == "claude-v35-wdpa"


def test_no_marker_falls_back_to_the_cli_major():
    with tempfile.TemporaryDirectory() as d:
        assert names.marker_version(4242, Path(d)) is None                       # no file
        (Path(d) / "4244").write_text("garbage")
        assert names.marker_version(4244, Path(d)) is None                       # unreadable: not a guess
        assert names.marker_version(None, Path(d)) is None                       # no claude pid
    assert names.rename_needed(agent("claude-v36-wdpa"), "2", None) == "claude-v2-wdpa"
    assert names.target_name("wD:pA", None, None) == "claude-wdpa"


def test_claude_pid_is_the_panes_own():
    #  shell 10 -> claude 11 -> zsh 12 (a tool shell, not a pane's claude)
    #  shell 20 -> nvim 21 -> claude 22 (claude in nvim's :terminal)
    #  shell 30 -> claude 31, claude 32 (ambiguous: no guess)
    t = {11: (10, "claude"), 12: (11, "zsh"), 21: (20, "nvim"), 22: (21, "claude"),
         31: (30, "claude"), 32: (30, "claude"), 41: (40, "zsh")}
    assert names.claude_pid_under(10, t) == 11
    assert names.claude_pid_under(20, t) == 22
    assert names.claude_pid_under(30, t) is None
    assert names.claude_pid_under(40, t) is None
    assert names.claude_pid_under(None, t) is None


def test_hook_writes_once_per_process():
    """Runs the real SessionStart hook into a temp marker dir. It finds its
    claude ancestor (this test runs under one when run from a claude pane) and
    never overwrites: /clear or compaction later in the process keep the
    version the process started with."""
    me, pid = os.getpid(), None
    while me > 1:
        out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(me)], capture_output=True, text=True).stdout.split(None, 1)
        if len(out) < 2:
            break
        if os.path.basename(out[1].strip()) == "claude":
            pid = me
            break
        me = int(out[0])
    if pid is None:
        print("skip test_hook_writes_once_per_process: not running under claude")
        return
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, CLAUDE_CONFIG_MARKERS=d)
        r = subprocess.run(["sh", str(HOOK)], capture_output=True, text=True, env=env)
        assert r.returncode == 0 and r.stdout == "", r                          # SessionStart stdout would reach the model
        want = (Path.home() / ".dotfiles/config/omp/VERSION").read_text().strip()
        assert (Path(d) / str(pid)).read_text().strip() == want
        (Path(d) / str(pid)).write_text("35\n")                                 # as if started before a bump
        subprocess.run(["sh", str(HOOK)], env=env)
        assert (Path(d) / str(pid)).read_text().strip() == "35"                 # not rewritten


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        fn()
        print(f"ok {name}")
