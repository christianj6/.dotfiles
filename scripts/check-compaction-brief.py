#!/usr/bin/env python3
"""Check that the owner's compaction brief is in place and loaded, for omp and Claude.

    python3 scripts/check-compaction-brief.py

The one source is config/agents/compaction-brief.md. Repo checks (exit 1 on any
failure):
  - its five items appear verbatim in both context files (Claude's CLAUDE.md,
    omp's APPEND_SYSTEM.md);
  - the Claude PreCompact hook prints it (stdout = custom compact instructions);
  - the omp extension, run under bun with a stand-in api, returns it from its
    session.compacting handler;
  - settings.json wires the hook and the threshold env var; config.yml sets
    compaction.thresholdPercent, and the installed omp's settings schema has
    that key (so it is read, not invented).
Live checks (reported, not failing): the files the running tools load resolve
into this repo, i.e. what a new session actually reads.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOME = Path.home()
BRIEF = REPO / "config/agents/compaction-brief.md"
fails: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        fails.append(what)


def items(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if l.strip()[:2] in ("1.", "2.", "3.", "4.", "5.")]


def main() -> int:
    brief = BRIEF.read_text().strip()
    five = items(brief)
    check(len(five) == 5 and brief.startswith("## Compact Instructions"), f"{BRIEF.relative_to(REPO)}: five items")
    for rel in ("config/claude/CLAUDE.md", "config/omp/context-files/APPEND_SYSTEM.md"):
        text = (REPO / rel).read_text()
        missing = [i for i in five if i not in text]
        check(not missing and "Compact Instructions" in text, f"{rel}: the five items verbatim" + (f" (missing {missing})" if missing else ""))

    hook = subprocess.run(["bash", str(REPO / "config/claude/hooks/compaction-brief.sh")], capture_output=True, text=True)
    check(hook.returncode == 0 and hook.stdout.strip() == brief, "Claude PreCompact hook prints the brief (exit 0)")

    bun = shutil.which("bun")
    if bun:
        with tempfile.TemporaryDirectory() as d:
            harness = Path(d) / "h.ts"
            harness.write_text(
                f'import ext from "{REPO}/config/omp/extensions/omp-compaction-brief.ts";\n'
                "const handlers: Record<string, Function> = {};\n"
                "ext({ on: (ev: string, fn: Function) => { handlers[ev] = fn; } });\n"
                'const r = handlers["session.compacting"]?.({ type: "session.compacting", sessionId: "s", messages: [] });\n'
                "console.log(JSON.stringify(r ?? null));\n")
            run = subprocess.run([bun, str(harness)], capture_output=True, text=True)
        try:
            got = json.loads(run.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            got = None
        check(isinstance(got, dict) and got.get("context") == [brief],
              "omp extension: session.compacting returns the brief as summarizer context")
    else:
        check(False, "omp extension: bun not found, could not run it")

    settings = json.loads((REPO / "config/claude/settings.json").read_text())
    pre = [h.get("command", "") for m in settings.get("hooks", {}).get("PreCompact", []) for h in m.get("hooks", [])]
    check(any("compaction-brief.sh" in c for c in pre), "settings.json: PreCompact runs the hook")
    pct = settings.get("env", {}).get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    check(pct is not None and 0 < int(pct) < 90, f"settings.json: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE={pct}")

    cfg = (REPO / "config/omp/config.yml").read_text()
    try:
        import yaml  # type: ignore
        tp = (yaml.safe_load(cfg).get("compaction") or {}).get("thresholdPercent")
    except ImportError:
        tp = 66 if "thresholdPercent: 66" in cfg else None
    check(tp is not None and 0 < int(tp) < 90, f"config.yml: compaction.thresholdPercent={tp}")
    omp = shutil.which("omp")
    if omp:
        root = Path(os.path.realpath(omp)).parent.parent
        schema = root / "src/config/settings-schema.ts"
        check(schema.is_file() and '"compaction.thresholdPercent"' in schema.read_text(),
              "installed omp reads compaction.thresholdPercent (its settings schema has the key)")

    print("\nlive (what a new session loads):")
    for link, target in (
        (HOME / ".claude/CLAUDE.md", REPO / "config/claude/CLAUDE.md"),
        (HOME / ".claude/settings.json", REPO / "config/claude/settings.json"),
        (HOME / ".omp/agent/APPEND_SYSTEM.md", REPO / "config/omp/context-files/APPEND_SYSTEM.md"),
        (HOME / ".omp/agent/config.yml", REPO / "config/omp/config.yml"),
        (HOME / ".omp/agent/extensions/omp-compaction-brief.ts", REPO / "config/omp/extensions/omp-compaction-brief.ts"),
    ):
        ok = link.exists() and Path(os.path.realpath(link)) == target.resolve()
        print(("  loaded     " if ok else "  NOT LINKED ") + f"~/{link.relative_to(HOME)}" + ("" if ok else "  (run setup.sh)"))

    print(f"\n{'OK' if not fails else f'{len(fails)} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
