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


for name, fn in list(globals().items()):
    if name.startswith("test_"):
        fn()
        print(f"ok {name}")
