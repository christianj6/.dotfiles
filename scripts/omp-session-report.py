#!/usr/bin/env python3
"""omp-session-report — cost/effort report for an omp session.

Usage:
  omp-session-report [repo-path]           # latest session for that repo
  omp-session-report [repo-path] --all     # all sessions for that repo
  omp-session-report [repo-path] --json    # machine-readable (paste to orchestrator)

Default repo-path: $PWD. The session dir is derived using omp's own
naming (verified against all live session dirs).
"""

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

HOME = Path.home()
SESSIONS_DIR = HOME / ".omp" / "agent" / "sessions"


def session_dirs_for(cwd: str):
    """Session directory names for a repo path — omp uses the same
    dash-wrap variants documented in omp-peer's find_session_file.
    Handles the macOS /tmp -> /private/tmp realpath and both wrap forms."""
    real = os.path.realpath(cwd)
    if real.startswith(str(HOME)):
        # HOME-relative: leading slash kept -> -.dotfiles
        key = real[len(str(HOME)):].replace("/", "-")
        candidates = [key]
    else:
        # absolute outside HOME: double-wrap --private-tmp-x--
        stripped = real.strip("/")
        candidates = ["--" + stripped.replace("/", "-") + "--"]
    for c in candidates:
        d = SESSIONS_DIR / c
        if d.is_dir():
            yield d


def parse_transcript(path: Path) -> dict:
    turns = []
    tool_calls = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        try:
            e = json.loads(line)
        except Exception:
            continue
        m = e.get("message") or {}
        if m.get("role") != "assistant":
            continue
        u = m.get("usage") or {}
        if not u.get("totalTokens"):
            continue
        c = u.get("cost") or {}
        model = m.get("model") or "unknown"
        ts = e.get("timestamp") or ""
        reasoning = u.get("reasoningTokens", 0) or 0
        turns.append({
            "model": model,
            "input": u.get("input", 0),
            "output": u.get("output", 0),
            "cacheRead": u.get("cacheRead", 0),
            "cacheWrite": u.get("cacheWrite", 0),
            "reasoning": reasoning,
            "cost_input": c.get("input", 0),
            "cost_output": c.get("output", 0),
            "cost_cacheRead": c.get("cacheRead", 0),
            "cost_cacheWrite": c.get("cacheWrite", 0),
            "cost_total": c.get("total", 0),
            "timestamp": ts,
        })
        for blk in (m.get("content") or []):
            if isinstance(blk, dict) and blk.get("type") == "toolCall":
                args = blk.get("arguments") or {}
                desc = args.get("command") or args.get("file_path") or args.get("pattern") or ""
                tool_calls.append({"name": blk.get("name", "?"), "desc": str(desc)[:80]})
    return {"turns": turns, "tool_calls": tool_calls}


def fmt_tokens(n):
    return f"{n:,}"


def fmt_duration(seconds):
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def report_session(path: Path) -> dict:
    data = parse_transcript(path)
    turns = data["turns"]
    if not turns:
        return {"file": str(path), "error": "no usage data (no assistant turns with token counts)"}

    total_cost = sum(t["cost_total"] for t in turns)
    models = list(dict.fromkeys(t["model"] for t in turns))
    tool_counter = Counter(tc["name"] for tc in data["tool_calls"])

    first_ts = turns[0].get("timestamp") or turns[0].get("cost_input")
    last_ts = turns[-1].get("timestamp")
    # parse timestamps for duration
    try:
        from datetime import datetime
        t1 = datetime.fromisoformat(turns[0]["timestamp"].replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(turns[-1]["timestamp"].replace("Z", "+00:00"))
        duration_s = (t2 - t1).total_seconds()
    except Exception:
        duration_s = None

    agg = {
        "file": str(path),
        "requests": len(turns),
        "models": models,
        "duration_s": round(duration_s) if duration_s else None,
        "tokens": {
            "input": sum(t["input"] for t in turns),
            "output": sum(t["output"] for t in turns),
            "cacheRead": sum(t["cacheRead"] for t in turns),
            "cacheWrite": sum(t["cacheWrite"] for t in turns),
            "reasoning": sum(t["reasoning"] for t in turns),
        },
        "cost": {
            "input": round(sum(t["cost_input"] for t in turns), 4),
            "output": round(sum(t["cost_output"] for t in turns), 4),
            "cacheRead": round(sum(t["cost_cacheRead"] for t in turns), 4),
            "cacheWrite": round(sum(t["cost_cacheWrite"] for t in turns), 4),
            "total": round(total_cost, 4),
        },
        "tool_calls": len(data["tool_calls"]),
        "tool_breakdown": dict(tool_counter),
    }
    return agg


def print_report(agg: dict):
    print(f"  file: {agg['file']}")
    if "error" in agg:
        print(f"  {agg['error']}")
        return
    print(f"  model: {', '.join(agg['models'])}")
    print(f"  requests: {agg['requests']} | duration: {fmt_duration(agg['duration_s']) if agg.get('duration_s') else '?'}")
    t = agg["tokens"]
    print(f"  tokens: in {fmt_tokens(t['input'])} | out {fmt_tokens(t['output'])} | "
          f"cacheR {fmt_tokens(t['cacheRead'])} | cacheW {fmt_tokens(t['cacheWrite'])} | "
          f"thinking {fmt_tokens(t['reasoning'])}")
    c = agg["cost"]
    print(f"  cost: ${c['total']:.4f} "
          f"(in ${c['input']:.4f} + out ${c['output']:.4f} + "
          f"cacheR ${c['cacheRead']:.4f} + cacheW ${c['cacheWrite']:.4f})")
    tc = agg.get("tool_breakdown", {})
    if tc:
        tools_str = ", ".join(f"{k}:{v}" for k, v in sorted(tc.items(), key=lambda x: -x[1]))
        print(f"  tools ({agg['tool_calls']} calls): {tools_str}")




def aggregate(files):
    """Aggregate multiple transcript files into one report (e.g. a
    mixed-roles episode's plan + implement phases)."""
    turns, tool_calls = [], []
    for f in files:
        d = parse_transcript(f)
        turns.extend(d["turns"])
        tool_calls.extend(d["tool_calls"])
    turns.sort(key=lambda t: t.get("timestamp") or "")
    total_cost = sum(t["cost_total"] for t in turns)
    models = list(dict.fromkeys(t["model"] for t in turns))
    tool_counter = Counter(tc["name"] for tc in tool_calls)
    duration_s = None
    try:
        from datetime import datetime
        t1 = datetime.fromisoformat(turns[0]["timestamp"].replace("Z", "+00:00"))
        t2 = datetime.fromisoformat(turns[-1]["timestamp"].replace("Z", "+00:00"))
        duration_s = (t2 - t1).total_seconds()
    except Exception:
        pass
    return {
        "files": [str(f) for f in files],
        "requests": len(turns),
        "models": models,
        "duration_s": round(duration_s) if duration_s else None,
        "tokens": {
            "input": sum(t["input"] for t in turns),
            "output": sum(t["output"] for t in turns),
            "cacheRead": sum(t["cacheRead"] for t in turns),
            "cacheWrite": sum(t["cacheWrite"] for t in turns),
            "reasoning": sum(t["reasoning"] for t in turns),
        },
        "cost": {
            "input": round(sum(t["cost_input"] for t in turns), 4),
            "output": round(sum(t["cost_output"] for t in turns), 4),
            "cacheRead": round(sum(t["cost_cacheRead"] for t in turns), 4),
            "cacheWrite": round(sum(t["cost_cacheWrite"] for t in turns), 4),
            "total": round(total_cost, 4),
        },
        "tool_calls": len(tool_calls),
        "tool_breakdown": dict(tool_counter),
    }

def main():
    ap = argparse.ArgumentParser(prog="omp-session-report", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo", nargs="?", default=os.getcwd(), help="repo path (default: cwd)")
    ap.add_argument("--all", action="store_true", help="report all sessions for this repo")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    dirs = list(session_dirs_for(repo))
    if not dirs:
        print(f"omp-session-report: no session directory for {repo}", file=sys.stderr)
        sys.exit(1)

    files = []
    for d in dirs:
        files.extend(sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True))
    if not files:
        print(f"omp-session-report: no transcript files for {repo}", file=sys.stderr)
        sys.exit(1)

    if not args.all:
        # aggregate all transcript files in the session dir (multi-phase
        # episodes like plan→implement produce separate files)
        pass

    if args.json:
        if args.all:
            out = [report_session(f) for f in files]
        else:
            out = [aggregate(files)]
        print(json.dumps(out, indent=1))
        return

    print(f"omp session report — {repo}")
    for f in files:
        age = time.time() - f.stat().st_mtime
        age_str = f"({age/60:.0f}m ago)" if age < 86400 else f"({age/86400:.0f}d ago)"
        print(f"\n  {f.name} {age_str}")
        agg = report_session(f)
        if "error" in agg:
            print(f"  {agg['error']}")
            continue
        t = agg["tokens"]
        c = agg["cost"]
        print(f"  model: {', '.join(agg['models'])}")
        print(f"  requests: {agg['requests']} | duration: {fmt_duration(agg['duration_s']) if agg.get('duration_s') else '?'}")
        print(f"  tokens: in {fmt_tokens(t['input'])} | out {fmt_tokens(t['output'])} | "
              f"cacheR {fmt_tokens(t['cacheRead'])} | cacheW {fmt_tokens(t['cacheWrite'])} | "
              f"thinking {fmt_tokens(t['reasoning'])}")
        print(f"  cost: ${c['total']:.4f} "
              f"(in ${c['input']:.4f} + out ${c['output']:.4f} + "
              f"cacheR ${c['cacheRead']:.4f} + cacheW ${c['cacheWrite']:.4f})")
        tc = agg.get("tool_breakdown", {})
        if tc:
            tools_str = ", ".join(f"{k}:{v}" for k, v in sorted(tc.items(), key=lambda x: -x[1]))
            print(f"  tools ({agg['tool_calls']} calls): {tools_str}")


if __name__ == "__main__":
    main()
