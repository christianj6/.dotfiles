#!/usr/bin/env python3
"""How much of a session's work went to subagents: counts and the delegation ratio.

    python3 scripts/check-delegation.py <transcript.jsonl>   # one omp or claude session
    python3 scripts/check-delegation.py --omp [repo]          # newest omp session for repo (default $PWD)
    python3 scripts/check-delegation.py --claude [repo]       # newest claude session for repo
    python3 scripts/check-delegation.py --rules               # the rule is in both instruction files + the brief
    python3 scripts/check-delegation.py --selftest            # synthetic transcripts, both formats
    ... --strict                                              # exit 1 when the target is missed

docs/task-make-subagents-default.md. Same shape as the other check-*.py scripts.
Counts the PARENT session's tool calls (a subagent's own calls live in its own
transcript, which is the point):

  tool calls: 1876 bash, 206 edit/write, 1 task   -> delegation ratio 0.0%

  delegation ratio = subagent dispatches / (bash + reads + edit/write + dispatches)

plus the over-threshold turns: turns with more than READS_PER_TURN inline reads
(read/grep/glob tools, and read-like bash: cat, sed -n, grep, rg, ls, find, head,
tail, wc, git show/log/diff) and no subagent. That is the end-of-turn self-check.

TARGET (what "good" means, so "more" is measurable):
  - delegation ratio >= 5%   (about one dispatch per 20 parent calls);
  - over-threshold turns: 0, or each one explained in that turn's report.
"""

import json
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

READS_PER_TURN = 5
TARGET_RATIO = 0.05

SUBAGENT = {"task", "Task", "Agent"}
EDIT = {"edit", "write", "Edit", "Write", "MultiEdit", "NotebookEdit", "ast_edit"}
READ = {"read", "grep", "glob", "find", "Read", "Grep", "Glob", "LS"}
BASH = {"bash", "Bash"}
READ_BASH = re.compile(
    r"^\s*(?:cd\s+\S+\s*(?:&&|;)\s*)?(?:cat|sed\s+-n|grep|rg|ls|find|head|tail|wc|jq|"
    r"git\s+(?:show|log|diff|status|grep))\b")


def tool_calls(entry: dict):
    """(name, input) for each tool call in one transcript entry, omp or claude."""
    msg = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    if msg.get("role") != "assistant":
        return
    for b in msg.get("content") or []:
        if isinstance(b, dict) and b.get("type") in ("toolCall", "tool_use"):
            yield b.get("id"), b.get("name") or "", b.get("arguments") or b.get("input") or {}


def is_prompt(entry: dict) -> bool:
    """A user prompt (starts a turn), not a tool result or harness meta entry."""
    msg = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    if msg.get("role") != "user" or entry.get("isMeta"):
        return False
    c = msg.get("content")
    return not (isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c))


def kind(name: str, args: dict) -> str:
    if name in SUBAGENT:
        return "task"
    if name in EDIT:
        return "edit"
    if name in READ:
        return "read"
    if name in BASH:
        return "read" if READ_BASH.match(str(args.get("command") or "")) else "bash"
    return "other"


def measure(path: Path) -> dict:
    counts, seen = Counter(), set()
    turns, cur = [], None
    for line in path.open("rb"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        if is_prompt(e):
            cur = Counter()
            turns.append(cur)
            continue
        for cid, name, args in tool_calls(e):
            if cid and cid in seen:           # claude can repeat a streamed block
                continue
            seen.add(cid)
            k = kind(name, args)
            counts[k] += 1
            if cur is not None:
                cur[k] += 1
    work = counts["bash"] + counts["read"] + counts["edit"] + counts["task"]
    ratio = counts["task"] / work if work else 0.0
    over = [i + 1 for i, t in enumerate(turns) if t["read"] > READS_PER_TURN and t["task"] == 0]
    return {"counts": counts, "ratio": ratio, "turns": len(turns), "over": over,
            "ok": ratio >= TARGET_RATIO and not over}


def report(path: Path) -> dict:
    r = measure(path)
    c = r["counts"]
    print(f"{path.name}")
    print(f"tool calls: {c['bash'] + c['read']} bash+reads ({c['read']} read-like), {c['edit']} edit/write, "
          f"{c['task']} task   -> delegation ratio {r['ratio']:.1%}   (target >= {TARGET_RATIO:.0%})")
    print(f"turns: {r['turns']}; over threshold (> {READS_PER_TURN} inline reads, no subagent): "
          f"{len(r['over'])}" + (f"  e.g. turns {r['over'][:10]}" if r["over"] else ""))
    print("OK" if r["ok"] else "BELOW TARGET")
    return r


def newest(agent: str, repo: str) -> Path:
    real = Path(os.path.realpath(repo))
    home = Path.home()
    if agent == "claude":
        name = re.sub(r"[/.]", "-", str(real))
        files = [f for d in home.glob(".claude/projects/*") if d.name == name for f in d.glob("*.jsonl")]
    else:
        rel = str(real.relative_to(home)) if real.is_relative_to(home) else str(real)
        name = "-" + rel.replace("/", "-") if real.is_relative_to(home) else "--" + rel.strip("/").replace("/", "-") + "--"
        files = list((home / ".omp/agent/sessions" / name).glob("*.jsonl"))
    if not files:
        sys.exit(f"no {agent} session found for {real}")
    return max(files, key=lambda p: p.stat().st_mtime)


REPO = Path(__file__).resolve().parent.parent
SECTIONS = {  # file -> (section start, section end)
    "config/claude/CLAUDE.md": ("## Sub-agents for atomic context", "## Compaction"),
    "config/omp/context-files/APPEND_SYSTEM.md": ("- **Atomic context (sub-agents)", "- Correctness gates"),
}
MUST = ["More than ~3 reads/searches to answer one question → stop and dispatch it",
        "that is the trigger", "stays inline. This is a threshold, not a ban",
        "GOAL:", "WHERE:", "RULED OUT:", "RETURN:", "compressed result",
        "End-of-turn self-check", "check-delegation.py"]


def rules() -> int:
    """Both delegation sections carry the trigger and the brief, with no
    'prefer'/'consider' in them; the compaction brief re-states the ratio."""
    fails = 0
    for rel, (a, b) in SECTIONS.items():
        text = (REPO / rel).read_text()
        sec = text[text.index(a):text.index(b, text.index(a))]
        missing = [m for m in MUST if m not in sec]
        soft = re.findall(r"\b(?:prefer|consider)\w*", sec, re.I)
        ok = not missing and not soft
        print(("PASS " if ok else "FAIL ") + f"{rel}: trigger + brief" + (f" missing {missing}" if missing else "")
              + (f" soft words {soft}" if soft else ""))
        fails += not ok
    brief = (REPO / "config/agents/compaction-brief.md").read_text()
    ok = "delegation ratio" in brief and "check-delegation.py" in brief
    print(("PASS " if ok else "FAIL ") + "config/agents/compaction-brief.md: re-states the delegation ratio")
    fails += not ok
    print("OK" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


def selftest() -> int:
    """Both formats: counts, the dedupe, read-like bash, and the over-threshold turn."""
    def omp(name, **a):
        return {"message": {"role": "assistant", "content": [{"type": "toolCall", "id": None, "name": name, "arguments": a}]}}

    def cl(i, name, **a):
        return {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": i, "name": name, "input": a}]}}

    user = {"message": {"role": "user", "content": "do it"}}
    result = {"message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}}
    cases = {
        "omp": ([user] + [omp("read")] * 6 + [omp("bash", command="make"), omp("edit")]
                + [user, omp("task"), omp("read")] * 1,
                {"read": 7, "bash": 1, "edit": 1, "task": 1}, [1]),
        "claude": ([user, cl("a", "Bash", command="sed -n 1,5p f"), result, cl("a", "Bash", command="sed -n 1,5p f"),
                    cl("b", "Agent"), cl("c", "Write")],
                   {"read": 1, "task": 1, "edit": 1}, []),
    }
    bad = 0
    for name, (entries, want, over) in cases.items():
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
            r = measure(p)
        got = {k: v for k, v in r["counts"].items() if v}
        ok = got == want and r["over"] == over
        print(f"selftest {name}: {'ok' if ok else "FAIL got %s over=%s" % (got, r["over"])}")
        bad += not ok
    print("selftest OK" if not bad else f"selftest: {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--strict"]
    if "--rules" in args:
        sys.exit(rules())
    if "--selftest" in args:
        sys.exit(selftest())
    if args and args[0] in ("--omp", "--claude"):
        path = newest(args[0][2:], args[1] if len(args) > 1 else os.getcwd())
    elif args:
        path = Path(args[0])
    else:
        sys.exit(__doc__)
    r = report(path)
    sys.exit(1 if "--strict" in sys.argv and not r["ok"] else 0)
