#!/usr/bin/env python3
"""Agent-side privacy guard: keeps an agent from switching off the git hooks
of a repo that ships the privacy scanner (scripts/private-patterns.txt).

The scanning itself lives in the git hooks (.githooks/pre-commit,
commit-msg, pre-push -> scripts/check-private.py). They run when git runs,
on the content git actually commits and pushes, so a chained
`git add x && git commit` is covered. What an agent could still do is turn
them off. This blocks, for git commit/push in such a repo:
  - --no-verify (and commit's -n),
  - a hooksPath override (git -c core.hooksPath=..., or setting it to
    anything but .githooks),
  - a clone whose core.hooksPath isn't .githooks (setup.sh never ran: the
    hooks would not run at all).

The target repo is found from the agent's cwd, every `cd <dir>` in the
command, and every `git -C <dir>`.

One implementation for both harnesses:
  --claude          Claude Code PreToolUse hook (stdin: the hook JSON);
                    blocks with exit 2 and the reason on stderr
  --check CMD --cwd D   prints {"block": bool, "reason": str} (omp's
                    omp-privacy-guard extension)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

GIT_WRITE = re.compile(r"\bgit\b[^|;&]*?\b(commit|push)\b")
HOOKS = ".githooks"


def _expand(p: str, base: str) -> str:
    p = os.path.expandvars(os.path.expanduser(p.strip("'\"")))
    return p if os.path.isabs(p) else os.path.join(base, p)


def candidate_dirs(cmd: str, cwd: str) -> list[str]:
    dirs = [cwd]
    for m in re.finditer(r"\bcd\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)", cmd):
        dirs.append(_expand(m.group(1), cwd))
    for m in re.finditer(r"\bgit\s+(?:[^|;&]*?\s)?-C\s+(\"[^\"]+\"|'[^']+'|[^\s;&|]+)", cmd):
        dirs.append(_expand(m.group(1), cwd))
    return dirs


def guarded_repos(cmd: str, cwd: str) -> list[Path]:
    out: list[Path] = []
    for d in candidate_dirs(cmd, cwd):
        if not os.path.isdir(d):
            continue
        p = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        root = Path(p.stdout.strip()) if p.returncode == 0 else None
        if root and (root / "scripts" / "private-patterns.txt").exists() and root not in out:
            out.append(root)
    return out


def _git_segments(cmd: str) -> list[str]:
    """The parts of a command line that are git commit/push invocations."""
    return [s for s in re.split(r"&&|\|\||;|\||\n", cmd) if GIT_WRITE.search(s)]


def _words(seg: str) -> list[str]:
    try:
        return shlex.split(seg)
    except ValueError:
        return seg.split()


def _no_verify(seg: str) -> bool:
    """--no-verify as an argument (a commit message that merely mentions it is fine)."""
    return "--no-verify" in _words(seg) or _commit_no_verify_short(seg)


def _commit_no_verify_short(seg: str) -> bool:
    """commit's -n (alone or bundled, e.g. -nm), outside quoted text."""
    words = _words(seg)
    if "commit" not in words:
        return False
    after = words[words.index("commit") + 1:]
    for w in after:
        if w == "--":
            break
        if re.fullmatch(r"-[A-Za-z]*n[A-Za-z]*", w) and not w.startswith("--"):
            # bundled short flags end at an option taking a value (-m, -F, -c, -C)
            flags = w[1:]
            for ch in flags:
                if ch == "n":
                    return True
                if ch in "mFcC":
                    break
    return False


def decide(cmd: str, cwd: str) -> tuple[bool, str]:
    if "git" not in cmd:
        return False, ""
    sets_hooks = re.search(r"\bgit\b[^|;&]*\bconfig\b[^|;&]*\bcore\.hookspath\b\s*(\S+)?", cmd, re.I)
    segments = _git_segments(cmd)
    if not segments and not sets_hooks:
        return False, ""
    repos = guarded_repos(cmd, cwd)
    if not repos:
        return False, ""
    where = ", ".join(str(r) for r in repos)
    if sets_hooks and (sets_hooks.group(1) or "").strip("'\"") not in ("", HOOKS):
        return True, f"core.hooksPath must stay {HOOKS} in {where}: the privacy hooks live there."
    for seg in segments:
        if _no_verify(seg):
            return True, (f"--no-verify skips the privacy hooks of {where} (a PUBLIC repo). Commit without it; "
                          "if a finding is wrong, tune scripts/private-patterns.txt with the owner.")
        if re.search(r"core\.hookspath", seg, re.I):
            return True, f"overriding core.hooksPath would skip the privacy hooks of {where}."
    if segments:
        for r in repos:
            p = subprocess.run(["git", "-C", str(r), "config", "core.hooksPath"], capture_output=True, text=True)
            if p.stdout.strip() != HOOKS:
                return True, (f"{r} has core.hooksPath={p.stdout.strip() or '(unset)'}, so its privacy hooks would not run. "
                              f"Run: git -C {r} config core.hooksPath {HOOKS}  (setup.sh does this).")
    return False, ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--claude", action="store_true")
    ap.add_argument("--check")
    ap.add_argument("--cwd", default=os.getcwd())
    args = ap.parse_args()
    if args.claude:
        try:
            ev = json.load(sys.stdin)
        except ValueError:
            return
        if ev.get("tool_name") not in (None, "Bash"):
            return
        block, reason = decide(str((ev.get("tool_input") or {}).get("command") or ""), ev.get("cwd") or os.getcwd())
        if block:
            print("Privacy guard: " + reason, file=sys.stderr)
            sys.exit(2)
        return
    if args.check is not None:
        block, reason = decide(args.check, args.cwd)
        print(json.dumps({"block": block, "reason": reason}))
        return
    ap.error("choose --claude or --check")


if __name__ == "__main__":
    main()
