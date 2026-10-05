#!/usr/bin/env python3
"""Privacy scanner for the public ~/.dotfiles repo.

The repo is public (fresh-VM clone without auth), so private content must
never land in tracked files: credential values, home-anchored private
paths, and personal planning/transcript content. Patterns live in
private-patterns.txt next to this file (owner's tuning knob); project
names and one-line board bookkeeping are explicitly fine.

Modes:
  --staged        scan staged changes (added lines; whole content for new
                  files) -- used by .githooks/pre-commit and the
                  omp-privacy-guard extension
  --all           scan every tracked file (manual audit)
  paths...        scan those files/directories directly

Exit codes: 0 clean, 1 findings (printed to stderr as file:line [label]).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PATTERNS_FILE = Path(__file__).resolve().parent / "private-patterns.txt"
MAX_FILE_BYTES = 2_000_000  # don't choke on vendored blobs


def git(*args: str) -> str:
    p = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"check-private: git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout


def load_patterns() -> list[tuple[str, str, "re.Pattern[str]"]]:
    import re

    pats: list[tuple[str, str, "re.Pattern[str]"]] = []
    label = "unlabeled"
    for raw in PATTERNS_FILE.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            label = line.lstrip("# ").strip() or label
            continue
        if line.startswith("!"):
            pats.append(("ALLOW", label, re.compile(line[1:].strip())))
        else:
            pats.append(("DENY", label, re.compile(line)))
    if not any(kind == "DENY" for kind, _, _ in pats):
        sys.exit("check-private: no DENY patterns loaded - refusing to run vacuous")
    return pats


def scan_text(path: str, text: str, pats) -> list[str]:
    findings: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not any(p.search(line) for kind, _, p in pats if kind == "DENY"):
            continue
        if any(p.search(line) for kind, _, p in pats if kind == "ALLOW"):
            continue
        hit = next((lbl for kind, lbl, p in pats if kind == "DENY" and p.search(line)), "?")
        findings.append(f"{path}:{i}: [{hit}] {line.strip()[:120]}")
    return findings


def scan_file(rel: str, pats) -> list[str]:
    abs_path = REPO / rel
    try:
        if abs_path.stat().st_size > MAX_FILE_BYTES:
            return []
        text = abs_path.read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(rel, text, pats)


def staged_files() -> list[str]:
    return [l for l in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if l]


def in_head(rel: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"HEAD:{rel}"],
        capture_output=True,
    ).returncode == 0


def scan_line(path: str, lineno: int, line: str, pats) -> list[str]:
    """Scan one line of known number; findings reference the real line."""
    if not any(p.search(line) for kind, _, p in pats if kind == "DENY"):
        return []
    if any(p.search(line) for kind, _, p in pats if kind == "ALLOW"):
        return []
    hit = next((lbl for kind, lbl, p in pats if kind == "DENY" and p.search(line)), "?")
    return [f"{path}:{lineno}: [{hit}] {line.strip()[:120]}"]


def scan_staged(pats) -> list[str]:
    findings: list[str] = []
    for rel in staged_files():
        if rel == "scripts/private-patterns.txt":
            continue  # the pattern file quotes its own regexes
        if not in_head(rel):
            findings.extend(scan_file(rel, pats))  # new file: whole content
            continue
        diff = git("diff", "--cached", "-U0", "--", rel)
        lineno = 0
        for l in diff.splitlines():
            if l.startswith("@@"):
                lineno = int(l.split()[2].lstrip("+").split(",")[0])
            elif l.startswith("+") and not l.startswith("+++"):
                findings.extend(scan_line(rel, lineno, l[1:], pats))
                lineno += 1
            elif l.startswith("-") or l.startswith("+++") or l.startswith("---"):
                continue
            else:
                lineno += 1
    return findings


def scan_all(pats) -> list[str]:
    findings: list[str] = []
    for rel in git("ls-files", "-z").split("\0"):
        if not rel or rel == "scripts/private-patterns.txt":
            continue
        findings.extend(scan_file(rel, pats))
    return findings


def scan_paths(paths: list[str], pats) -> list[str]:
    findings: list[str] = []
    for raw in paths:
        root = Path(raw)
        it = root.rglob("*") if root.is_dir() else [root]
        for f in it:
            if not f.is_file() or ".git" in f.parts:
                continue
            try:
                if f.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = f.read_text(errors="replace")
            except OSError:
                continue
            findings.extend(scan_text(str(f), text, pats))
    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()

    pats = load_patterns()
    if args.staged:
        findings = scan_staged(pats)
    elif args.all:
        findings = scan_all(pats)
    elif args.paths:
        findings = scan_paths(args.paths, pats)
    else:
        sys.exit("check-private: choose --staged, --all, or give paths")

    if findings:
        print(f"check-private: {len(findings)} finding(s) - private content must not land in this PUBLIC repo:", file=sys.stderr)
        for f in findings:
            print("  " + f, file=sys.stderr)
        print("Tune scripts/private-patterns.txt (with the owner) or remove the content.", file=sys.stderr)
        sys.exit(1)
    print("check-private: clean")


if __name__ == "__main__":
    main()
