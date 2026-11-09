#!/usr/bin/env python3
"""Check that the coordinator role chain is in place and nothing contradicts it.

    python3 scripts/check-coordinator-role.py             # check the repo (exit 1 on failure)
    python3 scripts/check-coordinator-role.py --selftest  # prove the check fails when the block goes

Same shape as scripts/check-compaction-brief.py (docs/task-enforce-coordinator-role.md):
  1. APPEND_SYSTEM.md opens with the ROLE CHAIN block: within its first 20 lines,
     coordinator -> decide / spec / dispatch / verify, "claude + its subagents" do
     the reading, research and code, subagents return a compressed result;
  2. the "editing a repo file from your own session is a PROCESS DEFECT" line;
  3. the compaction brief re-states the role chain, so a compaction restores it;
  4. claude's CLAUDE.md carries the mirroring duty (claude does the doing and
     delegates within itself);
  5. no context file implies the coordinator may implement;
  6. a spawned subagent is still exempt (it is the worker; it does not delegate).
"""

import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPEND = "config/omp/context-files/APPEND_SYSTEM.md"
RULES = "config/omp/context-files/RULES.md"
BRIEF = "config/agents/compaction-brief.md"
CLAUDE = "config/claude/CLAUDE.md"

HEAD_LINES = 20
BLOCK = [  # (what, regex) -- all must match within the first HEAD_LINES of APPEND_SYSTEM.md
    ("the ROLE CHAIN heading", r"^## ROLE CHAIN"),
    ("'You are the COORDINATOR'", r"You are the COORDINATOR\. You do not implement"),
    ("decide", r"^\s*- decide what should happen and why"),
    ("write the spec", r"^\s*- write the spec \(paths, change, acceptance\) to a file"),
    ("dispatch", r"^\s*- dispatch it to claude in this project, or to @task subagents"),
    ("verify", r"^\s*- verify the result against the spec, and own the verdict"),
    ("claude + its subagents do the work", r"claude \+ its subagents are the ones who read, research, and write code"),
    ("compressed result", r"compressed result, never their working narrative"),
    ("the PROCESS DEFECT line", r"Editing a repo file from your own session is a PROCESS DEFECT"),
]
# Phrasings that let the coordinator implement (the ones fixed in this change, and
# the obvious general shapes). Checked in the omp context files.
CONTRADICTIONS = [
    r"implementing directly for several",
    r"the implementation share",
    r"you (?:may|can) (?:implement|edit|write code|fix it)",
    r"implement it yourself",
    r"(?<!not )you writ(?:e|ing) the code",
    r"Never spend more than 3 consecutive turns on pure research",
]


def run(root: Path) -> list[str]:
    fails: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("PASS " if ok else "FAIL ") + what)
        if not ok:
            fails.append(what)

    append = (root / APPEND).read_text()
    head = "\n".join(append.splitlines()[:HEAD_LINES])
    for what, rx in BLOCK:
        check(bool(re.search(rx, head, re.M)), f"{APPEND} first {HEAD_LINES} lines: {what}")
    check(re.search(r"spawned task subagent skips this block", head) is not None
          and "Do NOT delegate further" in append,
          f"{APPEND}: a spawned subagent is exempt and does not delegate further")

    brief = (root / BRIEF).read_text()
    check("restate the role chain" in brief and "process defect" in brief
          and "claude and its subagents read, research and write code" in brief,
          f"{BRIEF}: re-states the role chain")

    claude = (root / CLAUDE).read_text()
    check("Your duty is the doing" in claude and "reading, the research and the coding" in claude
          and "Delegate within yourself" in claude,
          f"{CLAUDE}: the mirroring duty (claude does the doing, delegates within itself)")
    check("restate the role chain" in claude, f"{CLAUDE}: its brief copy re-states the role chain")

    for rel in (APPEND, RULES):
        text = (root / rel).read_text()
        hits = [rx for rx in CONTRADICTIONS if re.search(rx, text, re.I)]
        check(not hits, f"{rel}: nothing implies the coordinator may implement" + (f" (found {hits})" if hits else ""))

    print(f"\n{'OK' if not fails else f'{len(fails)} FAILED'}")
    return fails


def selftest() -> int:
    """The check must fail when the role block is deleted, the defect line is
    dropped, or an old contradiction comes back. Runs on a temp copy."""
    cases = {
        "role block deleted": lambda s: re.sub(r"## ROLE CHAIN.*?(?=## Your role)", "", s, flags=re.S),
        "defect line dropped": lambda s: s.replace("Editing a repo file from your own session is a PROCESS DEFECT", "Editing is discouraged"),
        "contradiction back": lambda s: s + "\nIf you catch yourself implementing directly for several consecutive turns, stop.\n",
    }
    bad = 0
    for name, mutate in cases.items():
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel in (APPEND, RULES, BRIEF, CLAUDE):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(REPO / rel, root / rel)
            p = root / APPEND
            p.write_text(mutate(p.read_text()))
            print(f"--- selftest: {name}")
            fails = run(root)
        ok = bool(fails)
        print(f"selftest {name}: {'check FAILED as it must' if ok else 'CHECK DID NOT FAIL'}\n")
        bad += not ok
    print("selftest OK" if not bad else f"selftest: {bad} case(s) not caught")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(1 if run(REPO) else 0)
