#!/usr/bin/env python3
"""omp-peer -- transcript-confirmed agent-to-agent messaging over herdr.

Why not `herdr agent prompt --wait`? omp lifecycle state reaches herdr via a
~3s transcript-polling watcher, so fast turns finish BETWEEN polls and --wait
false-stalls (agent_prompt_stalled) even when the exchange fully succeeded
(verified live 2026-09-06). omp-peer fires the prompt and confirms against
omp's own session transcript instead: the sent text must appear as a user
entry in the peer's newest session file (delivery proof), then --wait-reply
keeps polling for the next assistant entry that carries a text block (the
reply), the same needle-confirm pattern agent-discord's relay has used in
production since 2026-09-05.

Usage:
  omp-peer send <target> "<text>" [--wait-reply]
                [--confirm-timeout S] [--reply-timeout S]

  target  herdr agent name or pane id currently hosting an agent
          (`herdr agent list` is the address book)
  send    fires `herdr agent prompt <target> <text>` (fire-only), then
          confirms the text landed in the peer's transcript.
  --wait-reply  additionally polls for the peer's next text-bearing
          assistant entry and prints it to stdout.
  Exit codes: 0 delivered (and replied with --wait-reply); 1 herdr/target
  error; 2 delivery not confirmed in --confirm-timeout; 3 no reply within
  --reply-timeout (usually the peer is stuck on an approval dialog -- omp
  approvals are UI-only and invisible to herdr; escalate to the human);
  4 peer's REPL not visible after toggling (nvim-nested peer) -- never
  typed anything.
stdout: "delivered <session-file>" (send) or the reply text (--wait-reply).
Progress goes to stderr.

Exit codes: 0 delivered (and replied with --wait-reply); 1 herdr/target
error; 2 delivery not confirmed in --confirm-timeout; 3 no reply within
--reply-timeout (usually the peer is stuck on an approval dialog -- omp
approvals are UI-only and invisible to herdr; escalate to the human).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
SESSIONS_DIR = HOME / ".omp" / "agent" / "sessions"
POLL_SECONDS = 2.0


def herdr(*args: str) -> tuple[int, str, str]:
    p = subprocess.run(["herdr", *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def agent_info(target: str) -> tuple[str, str]:
    """Resolve (cwd, pane_id) herdr has for an agent (name or pane id)."""
    rc, out, err = herdr("agent", "get", target)
    if rc != 0:
        print(f"omp-peer: agent get {target!r} failed: {(err or out).strip()}", file=sys.stderr)
        sys.exit(1)
    try:
        a = json.loads(out)["result"]["agent"]
        return a["cwd"], a["pane_id"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"omp-peer: unexpected agent get output: {exc}", file=sys.stderr)
        sys.exit(1)


REPL_MARKERS = re.compile(r"Prewalk|Opus|GLM|π")


def repl_visible(pane_id: str) -> bool:
    rc, out, _ = herdr("agent", "read", pane_id, "--source", "visible", "--lines", "10")
    return rc == 0 and bool(REPL_MARKERS.search((out or "")[-1200:]))


def ensure_repl_visible(pane_id: str) -> None:
    """Guard for REPL-nested peers (omp inside nvim): raw typing lands in
    whatever pane window has focus, so the omp input box must be visible
    before sending. Same remedy as agent-discord's relay, verified live
    2026-09-05: toggle the REPL with ctrl+a (the user's yarepl binding);
    open-but-unfocused hides on the first toggle and reopens on the second.
    Bounded at two toggles, then refuse."""
    if repl_visible(pane_id):
        return
    for _ in range(2):
        print("omp-peer: REPL not visible -- toggling open (ctrl+a)", file=sys.stderr)
        herdr("pane", "send-keys", pane_id, "ctrl+a")
        time.sleep(0.8)
        if repl_visible(pane_id):
            return
    print("omp-peer: could not bring the peer's REPL into view after 2 toggles; refusing to type blind", file=sys.stderr)
    sys.exit(4)


def candidate_keys(cwd: str):
    """omp's transcript dir naming, verified against all six live dirs in
    ~/.omp/agent/sessions on 2026-09-06:
      HOME-relative: leading slash kept, / -> -   (/Users/me/.dotfiles -> -.dotfiles)
      absolute:      doubled dash wrap            (/private/tmp/x -> --private-tmp-x--)
    The second yield per branch covers hypothetical unwrapped/wrapped
    variants; the observed forms come first."""
    if cwd.startswith(str(HOME)):
        rel = cwd[len(str(HOME)):]
        yield "-" + rel.replace("/", "-")
        yield rel.replace("/", "-")
    else:
        yield "--" + cwd.strip("/").replace("/", "-") + "--"
        yield "-" + cwd.replace("/", "-")


def find_session_file(cwd: str) -> Path | None:
    """Newest top-level transcript for a cwd. Top-level only: omp also
    writes per-session sidecar subdirs (<session>/__advisor.jsonl) whose
    entries are NOT the peer's own conversation and would poison both
    needle-confirm and reply detection."""
    for candidate in candidate_keys(cwd):
        d = SESSIONS_DIR / candidate
        if d.is_dir():
            files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                return files[0]
    return None


def entries_of(path: Path) -> list[dict]:
    """Parsed transcript entries; a torn final line is skipped, never
    mis-parsed (same rule as the watcher's backward scan)."""
    out = []
    try:
        for line in path.read_text(errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except FileNotFoundError:
        pass
    return out


def entry_text(e: dict) -> str:
    msg = e.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return ""
    return " ".join(
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
    )


def wait_for(
    label: str,
    cwd: str,
    timeout: float,
    match,  # (entries, start_idx) -> int | None
) -> tuple[Path, int]:
    """Poll the newest session file for `match` over fresh entries only.
    Returns (file, matched_index)."""
    deadline = time.monotonic() + timeout
    tracked: Path | None = find_session_file(cwd)
    baseline = len(entries_of(tracked)) if tracked else 0
    print(f"omp-peer: waiting for {label} (timeout {timeout:.0f}s) ...", file=sys.stderr)
    while time.monotonic() < deadline:
        current = find_session_file(cwd)
        if current is not None:
            if tracked is None or current != tracked:
                tracked, baseline = current, 0
            entries = entries_of(tracked)
            hit = match(entries, baseline)
            if hit is not None:
                return tracked, hit
            if len(entries) > baseline:
                baseline = len(entries)  # only ever move forward
        time.sleep(POLL_SECONDS)
    print(f"omp-peer: {label} not seen within {timeout:.0f}s", file=sys.stderr)
    sys.exit(2 if label == "delivery" else 3)


def main() -> None:
    ap = argparse.ArgumentParser(prog="omp-peer", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("send", help="fire + transcript-confirm a message to a peer agent")
    sp.add_argument("target", help="herdr agent name or pane id")
    sp.add_argument("text", help="instruction text (sent verbatim as a user message)")
    sp.add_argument("--wait-reply", action="store_true",
                    help="also wait for the peer's next text-bearing assistant entry and print it")
    sp.add_argument("--confirm-timeout", type=float, default=30.0)
    sp.add_argument("--reply-timeout", type=float, default=300.0)
    sp.add_argument("--no-guard", action="store_true",
                    help="skip the REPL visibility guard (standalone agent panes)")
    args = ap.parse_args()

    cwd, pane_id = agent_info(args.target)

    rc, out, err = herdr("agent", "prompt", args.target, args.text)
    raw = False
    if rc != 0:
        if "agent_not_ready" in (err or "") + (out or ""):
            # REPL-nested peer (omp inside nvim): herdr refuses because the
            # pane foreground is nvim, not the agent. Deliver raw, bot-style.
            raw = True
            print("omp-peer: agent prompt refused (nested REPL) -- raw pane delivery", file=sys.stderr)
            if not args.no_guard:
                ensure_repl_visible(pane_id)
            payload = "\x1b[200~" + args.text + "\x1b[201~"
            rc2, _, err2 = herdr("pane", "send-text", pane_id, payload)
            if rc2 != 0:
                print(f"omp-peer: pane send-text failed: {(err2 or '').strip()}", file=sys.stderr)
                sys.exit(1)
            time.sleep(0.3)
            herdr("pane", "send-keys", pane_id, "enter")
        else:
            print(f"omp-peer: agent prompt failed: {(err or out).strip()}", file=sys.stderr)
            sys.exit(1)

    needle = re.sub(r"\s+", " ", args.text.strip())[:24]

    def is_delivery(entries: list[dict], start: int) -> int | None:
        for i in range(start, len(entries)):
            e = entries[i]
            msg = e.get("message") or {}
            if msg.get("role") == "user" and needle in re.sub(r"\s+", " ", entry_text(e)):
                return i
        return None

    def is_reply(entries: list[dict], start: int) -> int | None:
        for i in range(start, len(entries)):
            e = entries[i]
            msg = e.get("message") or {}
            if msg.get("role") == "assistant" and entry_text(e).strip():
                return i
        return None

    try:
        sfile, idx = wait_for("delivery", cwd, args.confirm_timeout, is_delivery)
    except SystemExit as exc:
        if exc.code == 2 and raw:
            # the first Enter can be dropped right after a paste block -- send one more, then judge
            print("omp-peer: retrying enter", file=sys.stderr)
            herdr("pane", "send-keys", pane_id, "enter")
            sfile, idx = wait_for("delivery", cwd, args.confirm_timeout, is_delivery)
        else:
            raise
    print(f"delivered {sfile}", file=sys.stderr)

    if not args.wait_reply:
        print(f"delivered {sfile}")
        return

    base = idx + 1

    def reply_match(entries: list[dict], start: int) -> int | None:
        return is_reply(entries, max(start, base))

    rfile, ridx = wait_for("reply", cwd, args.reply_timeout, reply_match)
    entries = entries_of(rfile)
    print(entry_text(entries[ridx]).strip())


if __name__ == "__main__":
    main()
