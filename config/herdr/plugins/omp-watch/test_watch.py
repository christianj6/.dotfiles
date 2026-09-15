#!/usr/bin/env python3
"""Regression tests for watch.py's infer_state() verdict table.

Plain asserts, no framework: `python3 test_watch.py` runs everything and
prints one line per group. These pin the OBSERVABLE contract that matters
to the herdr sidebar: which transcript tails mean "working", which mean
"idle", and which are ambiguous ("maybe_idle" -- gated on file quiescence
by main(), see watch.py IDLE_GRACE_SECONDS) -- and which mean the turn
FAILED outright ("blocked": stopReason "error", the model/provider
failure path added 2026-09-06; "aborted" is deliberately NOT blocked).

The text-only-assistant history here is the point: 2026-09-04 concluded
"text without toolCall = finished turn"; 2026-09-05 proved that wrong
(omp's loop continues the turn after interim text-only answers via
prewalk-continue / plan approvals / async subagent results -- 109
confirmed continuations vs 861 genuine ends, byte-indistinguishable).
If you ever see "idle" being asserted for a text-only tail here, that is
a regression to the premature-done bug.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import watch  # noqa: E402


def msg(role, blocks):
    return {"type": "message", "message": {"role": role, "content": blocks}}


def block(btype):
    return {"type": btype}


def _tmp_jsonl(lines):
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "wb") as f:
        f.write(b"".join(lines))
    return Path(p)


def _msg_entry(role, blocks, text="x"):
    return json.dumps({"type": "message", "message": {"role": role, "content": [
        dict(b, text=text) if b.get("type") == "text" else dict(b) for b in blocks
    ]}}).encode()


def test_latest_verdict_survives_giant_entries():
    # The 2026-09-05 w5:p7 false-done: a 58KB toolResult as the newest
    # line made the old fixed 32KB window empty -> None -> default idle
    # while the agent worked. The scanner must classify by the newest
    # COMPLETE recognizable entry regardless of entry size.
    giant_tool_result = _msg_entry("toolResult", [block("text")], text="y" * 200_000)
    p = _tmp_jsonl([
        _msg_entry("user", [block("text")]), b"\n",
        giant_tool_result, b"\n",
    ])
    try:
        assert watch.latest_verdict(p) == "working"
    finally:
        p.unlink()


def test_latest_verdict_skips_giant_unrecognized_and_partial_tail():
    # A giant UNRECOGNIZED entry (e.g. a huge injected context message)
    # must fall back to the previous recognizable entry, and a final
    # line without its newline (writer mid-flush) must be skipped, never
    # mis-parsed.
    giant_unrecognized = json.dumps({"type": "custom_message", "customType": "vibe-mode-context",
                                     "content": "z" * 200_000}).encode()
    # 1) giant unrecognized last (terminated) -> falls back to the toolResult before it
    p = _tmp_jsonl([
        _msg_entry("user", [block("text")]), b"\n",
        _msg_entry("toolResult", [block("text")]), b"\n",
        giant_unrecognized, b"\n",
    ])
    try:
        assert watch.latest_verdict(p) == "working"
    finally:
        p.unlink()
    # 2) partial final line (no trailing newline) -> skipped
    p = _tmp_jsonl([
        _msg_entry("user", [block("text")]), b"\n",
        _msg_entry("toolResult", [block("text")]), b"\n",
        giant_unrecognized,  # deliberately no b"\n"
    ])
    try:
        assert watch.latest_verdict(p) == "working"
    finally:
        p.unlink()


def test_latest_verdict_maybe_idle_and_empty():
    p = _tmp_jsonl([
        _msg_entry("user", [block("text")]), b"\n",
        _msg_entry("assistant", [block("thinking"), block("text")]), b"\n",
    ])
    try:
        assert watch.latest_verdict(p) == "maybe_idle"
    finally:
        p.unlink()
    p = _tmp_jsonl([])
    try:
        assert watch.latest_verdict(p) is None
    finally:
        p.unlink()


def custom(custom_type):
    return {"type": "custom", "customType": custom_type}


def last(entries):
    return watch.infer_state(entries)


def test_unfinished_tails_are_working():
    # Every entry shape that means "the turn is still open" -- including
    # toolCall blocks embedded ATOMICALLY inside an assistant message
    # (Anthropic-style), which was the 2026-09-04 fix.
    cases = [
        [msg("user", [block("text")])],
        [msg("assistant", [block("toolCall")])],
        [msg("assistant", [block("thinking")])],  # reasoning, not answered
        [msg("assistant", [])],  # empty content: still reasoning
        [msg("assistant", [block("thinking"), block("text"), block("toolCall")])],
        [msg("assistant", [block("thinking"), block("toolCall")])],
        [msg("assistant", [block("text"), block("toolCall")])],
        [msg("toolResult", [block("text")])],  # agent loop must still react
        [custom("tool_execution_start")],
        # unrecognized entries never change the running verdict
        [msg("user", [block("text")]), {"type": "mode_change"}],
        [msg("user", [block("text")]), {"type": "custom_message", "customType": "prewalk-continue"}],
    ]
    for entries in cases:
        assert last(entries) == "working", (entries, last(entries))


def test_text_only_assistant_is_maybe_idle():
    # The premature-done bug class: a text-only assistant tail LOOKS
    # finished but omp's loop may continue it. It must come back as
    # "maybe_idle" (main() holds it working until the file goes quiet),
    # never as a hard "idle".
    for blocks in ([block("text")], [block("thinking"), block("text")], [block("text"), block("thinking")]):
        entries = [msg("user", [block("text")]), msg("assistant", blocks)]
        assert last(entries) == "maybe_idle", (blocks, last(entries))


def test_error_turns_are_blocked():
    # 2026-09-06: model/provider failures land as assistant entries with
    # stopReason "error" + content [] (verified against real OpenRouter
    # guardrail 404 transcripts, which also carry errorStatus/errorId/
    # errorMessage). The turn is dead and the agent needs input: herdr
    # "blocked", which notify.py turns into a Discord ping. Previously
    # these fell into the empty-content -> "working" branch and pinned
    # failed agents at working forever.
    error_entry = {"type": "message", "message": {
        "role": "assistant", "content": [], "stopReason": "error",
        "errorStatus": 404, "errorMessage": "404 provider not allowed"}}
    assert last([msg("user", [block("text")]), error_entry]) == "blocked"
    # partial streamed content + error is still an error
    error_entry["message"]["content"] = [block("text")]
    assert last([msg("user", [block("text")]), error_entry]) == "blocked"


def test_abort_is_not_blocked():
    # "Interrupted by user" (stopReason "aborted") ends the turn without
    # failing it: the agent waits for input like after any finished turn.
    entries = [
        msg("user", [block("text")]),
        {"type": "message", "message": {
            "role": "assistant", "content": [], "stopReason": "aborted",
            "errorMessage": "Interrupted by user"}},
    ]
    assert last(entries) == "maybe_idle"


def test_blocked_recovers_on_next_entry():
    # a new user message re-opens the turn; a successful retry resolves it
    error_entry = {"type": "message", "message": {
        "role": "assistant", "content": [], "stopReason": "error"}}
    assert last([error_entry, msg("user", [block("text")])]) == "working"
    assert last([error_entry, msg("assistant", [block("text")])]) == "maybe_idle"
    # a repeated error (omp's retry pair) stays blocked
    assert last([error_entry, dict(error_entry)]) == "blocked"


def test_latest_verdict_error_tail():
    p = _tmp_jsonl([
        _msg_entry("user", [block("text")]), b"\n",
        json.dumps({"type": "message", "message": {
            "role": "assistant", "content": [], "stopReason": "error",
            "errorStatus": 404}}).encode(), b"\n",
    ])
    try:
        assert watch.latest_verdict(p) == "blocked"
    finally:
        p.unlink()


def test_exit_and_empty():
    assert last([custom("session_exit")]) == "exit"
    # nothing recognizable -> None (main() then falls back to presence-idle)
    assert last([{"type": "mode_change"}]) is None
    assert last([]) is None


def test_last_recognizable_entry_wins():
    # A finished-looking tail followed by renewed activity reads working;
    # activity followed by a finished-looking tail reads maybe_idle.
    entries = [
        msg("user", [block("text")]),
        msg("assistant", [block("text")]),  # interim-looking
        custom("tool_execution_start"),  # turn continued
    ]
    assert last(entries) == "working"
    entries = [
        msg("user", [block("text")]),
        msg("assistant", [block("thinking"), block("text"), block("toolCall")]),
        msg("toolResult", [block("text")]),
        msg("assistant", [block("text")]),  # final-looking
    ]
    assert last(entries) == "maybe_idle"


def test_foreign_claim_detection():
    # A managed integration's agent-session claim (e.g. herdr:claude, left
    # by any claude process that inherited the pane's HERDR_PANE_ID) owns
    # the pane's agent slot: herdr accepts our reports with "ok" and never
    # applies them, freezing that pane's sidebar status (verified live
    # 2026-09-15 on w6:p4 -- our source AND never-used fresh sources both
    # no-ops, release-agent a no-op, claim persisted in session.json).
    # main() must recognise this exactly: warn once, skip the pane, and
    # never waste source rotations on it.
    assert watch.foreign_claim({}) is None
    assert watch.foreign_claim({"agent_session": None}) is None
    # our own reports never claim a session, but be explicit about the
    # base source and its rotation variants
    assert watch.foreign_claim({"agent_session": {"source": "custom:omp-watch"}}) is None
    assert watch.foreign_claim({"agent_session": {"source": "custom:omp-watch-r3"}}) is None
    # foreign claims, whatever the agent label
    assert watch.foreign_claim(
        {"agent_session": {"source": "herdr:claude", "agent": "claude"}}
    ) == "herdr:claude"
    assert watch.foreign_claim(
        {"agent_session": {"source": "herdr:omp", "agent": "omp"}}
    ) == "herdr:omp"


def test_registry_matches_is_the_sidebar_truth():
    # The registry is what the sidebar renders; these pairs must count as
    # converged (no report spam) vs diverged (report + eventual rotation).
    assert watch.registry_matches("working", "working")
    assert not watch.registry_matches("working", "idle")
    assert not watch.registry_matches("working", "done")  # done only pairs with idle
    assert not watch.registry_matches("working", "unknown")
    assert not watch.registry_matches("working", None)
    # idle: herdr renders an unviewed idle as "done".
    assert watch.registry_matches("idle", "idle")
    assert watch.registry_matches("idle", "done")
    assert not watch.registry_matches("idle", "working")
    # blocked pairs only with itself: a failed turn must not be rendered
    # as (or collapse into) idle/done anywhere in the pipeline.
    assert watch.registry_matches("blocked", "blocked")
    assert not watch.registry_matches("blocked", "idle")
    assert not watch.registry_matches("blocked", "working")
    # None/unknown is deliberately a MISMATCH even for idle: a pane absent
    # from the registry (fresh pane, or herdr server restart wiping it)
    # must be (re-)reported at least once or it never shows in the sidebar.
    assert not watch.registry_matches("idle", None)
    assert not watch.registry_matches("idle", "unknown")


def main():
    groups = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in groups:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"all {len(groups)} groups passed")


if __name__ == "__main__":
    main()
