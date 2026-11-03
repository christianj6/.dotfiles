#!/usr/bin/env python3
"""Privacy scanner for the public ~/.dotfiles repo.

The repo is public (fresh-VM clone without auth), so private content must
never land in tracked files: credential values, home-anchored private
paths, and personal planning/transcript content. Patterns live in
private-patterns.txt next to this file (owner's tuning knob); project
names and one-line board bookkeeping are explicitly fine.

Modes:
  --staged        scan staged changes, read from the INDEX (added lines;
                  the whole staged blob for new files) -- .githooks/pre-commit
  --commit-msg F  scan a commit message file -- .githooks/commit-msg
  --pre-push      scan every commit about to be pushed (added lines and
                  messages; git's pre-push stdin) -- .githooks/pre-push
  --all           scan every tracked file (manual audit)
  paths...        scan those files/directories directly

Nothing is skipped silently: staged and pushed content is scanned whatever
its size; --all and paths warn about a file too large to scan.

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


def denied(line: str, pats) -> str | None:
    """The label of the first DENY pattern the line matches, or None. An
    ALLOW match only covers its own span: it is cut out and the rest of the
    line is scanned again, so an allowed path never vouches for another
    private path on the same line."""
    if not any(p.search(line) for kind, _, p in pats if kind == "DENY"):
        return None
    rest = line
    for kind, _, p in pats:
        if kind == "ALLOW":
            rest = p.sub(" ", rest)
    return next((lbl for kind, lbl, p in pats if kind == "DENY" and p.search(rest)), None)


def scan_text(path: str, text: str, pats) -> list[str]:
    findings: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        findings.extend(scan_line(path, i, line, pats))
    return findings


def too_big(path: str) -> None:
    print(f"check-private: WARNING {path} is over {MAX_FILE_BYTES} bytes and was not scanned - review it by hand", file=sys.stderr)


def scan_file(rel: str, pats) -> list[str]:
    abs_path = REPO / rel
    try:
        if abs_path.stat().st_size > MAX_FILE_BYTES:
            too_big(rel)
            return []
        text = abs_path.read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_text(rel, text, pats)


def staged_blob(rel: str) -> str:
    """The file as it is staged (the index), never the working tree: what the
    commit will actually contain."""
    p = subprocess.run(["git", "-C", str(REPO), "cat-file", "blob", f":{rel}"], capture_output=True)
    if p.returncode != 0:
        sys.exit(f"check-private: cannot read the staged {rel}: {p.stderr.decode(errors='replace').strip()}")
    return p.stdout.decode(errors="replace")


def staged_files() -> list[str]:
    return [l for l in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if l]


def in_head(rel: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"HEAD:{rel}"],
        capture_output=True,
    ).returncode == 0


def scan_line(path: str, lineno: int, line: str, pats) -> list[str]:
    """Scan one line of known number; findings reference the real line."""
    hit = denied(line, pats)
    return [f"{path}:{lineno}: [{hit}] {line.strip()[:120]}"] if hit else []


def scan_staged(pats) -> list[str]:
    findings: list[str] = []
    for rel in staged_files():
        if rel == "scripts/private-patterns.txt":
            continue  # the pattern file quotes its own regexes
        if not in_head(rel):
            findings.extend(scan_text(rel, staged_blob(rel), pats))  # new file: the whole staged blob
            continue
        findings.extend(scan_patch(git("diff", "--cached", "-U0", "--no-color", "--", rel), pats))
    return findings


def scan_patch(patch: str, pats, where: str = "") -> list[str]:
    """Added lines of a unified diff (-U0), with their real line numbers."""
    findings: list[str] = []
    rel, lineno = "?", 0
    for l in patch.splitlines():
        if l.startswith("+++ "):
            rel = l[6:] if l.startswith("+++ b/") else l[4:]
        elif l.startswith("@@"):
            lineno = int(l.split()[2].lstrip("+").split(",")[0])
        elif l.startswith("+"):
            if rel != "scripts/private-patterns.txt":
                findings.extend(scan_line(where + rel, lineno, l[1:], pats))
            lineno += 1
        elif l.startswith((" ",)):
            lineno += 1
    return findings


def scan_message(label: str, text: str, pats) -> list[str]:
    findings: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line.startswith("#"):                     # git's own comment lines are stripped
            findings.extend(scan_line(label, i, line, pats))
    return findings


ZERO = "0" * 40


def pushed_commits(stdin_lines: list[str]) -> list[str]:
    """The commits a push publishes, from git's pre-push stdin
    (<local ref> <local sha> <remote ref> <remote sha> per line)."""
    revs: list[str] = []
    for line in stdin_lines:
        parts = line.split()
        if len(parts) != 4 or parts[1].strip("0") == "":
            continue                                    # a branch delete publishes nothing
        local, remote = parts[1], parts[3]
        spec = [local, "--not", "--remotes"] if remote.strip("0") == "" else [f"{remote}..{local}"]
        revs += [r for r in git("rev-list", *spec).splitlines() if r and r not in revs]
    return revs


def scan_commits(revs: list[str], pats) -> list[str]:
    findings: list[str] = []
    for rev in revs:
        short = rev[:9]
        findings.extend(scan_message(f"commit {short} message", git("log", "-1", "--format=%B", rev), pats))
        findings.extend(scan_patch(git("diff-tree", "-p", "-U0", "--no-color", "--root", "--no-commit-id", rev), pats, f"commit {short} "))
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
                    too_big(str(f))
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
    ap.add_argument("--commit-msg", metavar="FILE")
    ap.add_argument("--pre-push", action="store_true")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args()

    pats = load_patterns()
    if args.staged:
        findings = scan_staged(pats)
    elif args.commit_msg:
        findings = scan_message("commit message", Path(args.commit_msg).read_text(errors="replace"), pats)
    elif args.pre_push:
        findings = scan_commits(pushed_commits(sys.stdin.read().splitlines()), pats)
    elif args.all:
        findings = scan_all(pats)
    elif args.paths:
        findings = scan_paths(args.paths, pats)
    else:
        sys.exit("check-private: choose --staged, --commit-msg, --pre-push, --all, or give paths")

    if findings:
        print(f"check-private: {len(findings)} finding(s) - private content must not land in this PUBLIC repo:", file=sys.stderr)
        for f in findings:
            print("  " + f, file=sys.stderr)
        print("Tune scripts/private-patterns.txt (with the owner) or remove the content.", file=sys.stderr)
        sys.exit(1)
    print("check-private: clean")


if __name__ == "__main__":
    main()
