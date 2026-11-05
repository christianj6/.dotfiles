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
  omp-peer send <target> "<text>" [--wait-reply] [--from ROLE] [--dry-run]
                [--confirm-timeout S] [--reply-timeout S]

  target  herdr agent name or pane id currently hosting an agent
          (`herdr agent list` is the address book)
  send    fires `herdr agent prompt <target> <text>` (fire-only), then
          confirms the text landed in the peer's transcript.
  --wait-reply  additionally polls for the peer's next text-bearing
          assistant entry and prints it to stdout.

Sender tag (docs/design-message-tags.md): every message goes out with one
first line naming its sender, because a pane transcript records no sender
of its own (every entry is role "user"):

  [from:<role> project:<project> id:<name>]

  role     coordinator (the sender is an omp pane), worker (a claude pane),
           or --from <owner|coordinator|worker|harness|bro>
  project  the sender's repo folder name, leading dot dropped (the board's
           rule: .dotfiles -> dotfiles)
  id       the sender's herdr agent name

The sender is the pane in $HERDR_PANE_ID, looked up in `herdr agent list`.
Text that already starts with "[from:" goes out unchanged (never two tags).
With no sender pane and no --from, the text goes out untagged, with a
warning. --dry-run prints the final text and sends nothing.

Targets: omp panes confirm against ~/.omp session files; claude panes
against their own transcript (<session-id>.jsonl under CLAUDE_PROJECTS, the
session id herdr reports), where a message typed mid-turn shows as a queue
entry first.
  Exit codes: 0 delivered (and replied with --wait-reply); 1 herdr/target
  error; 2 delivery not confirmed in --confirm-timeout; 3 no reply within
  --reply-timeout (usually the peer is stuck on an approval dialog -- omp
  approvals are UI-only and invisible to herdr; escalate to the human);
  4 peer's REPL could not be brought into view (nvim-nested peer) --
  never typed anything.
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
CLAUDE_PROJECTS = HOME / ".claude" / "projects"
POLL_SECONDS = 2.0


def herdr(*args: str) -> tuple[int, str, str]:
    p = subprocess.run(["herdr", *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def agent_info(target: str) -> dict:
    """The agent record herdr has for a target (name or pane id): cwd,
    pane_id, agent kind, and agent_session for claude panes."""
    rc, out, err = herdr("agent", "get", target)
    if rc != 0:
        print(f"omp-peer: agent get {target!r} failed: {(err or out).strip()}", file=sys.stderr)
        sys.exit(1)
    try:
        a = json.loads(out)["result"]["agent"]
        a["cwd"], a["pane_id"]  # required
        return a
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"omp-peer: unexpected agent get output: {exc}", file=sys.stderr)
        sys.exit(1)


# ---- sender tag (docs/design-message-tags.md) --------------------------------

ROLES = ("owner", "coordinator", "worker", "harness", "bro")
ROLE_OF_KIND = {"omp": "coordinator", "claude": "worker"}
# The receiver's check (lifeview's prompt_provenance) anchors on the same
# prefix, so anything starting "[from:" is already tagged.
ALREADY_TAGGED = re.compile(r"^\s*\[from:")


def herdr_agents() -> list[dict]:
    rc, out, _ = herdr("agent", "list")
    if rc != 0:
        return []
    try:
        return json.loads(out)["result"]["agents"] or []
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def project_of(cwd: str) -> str:
    """The board's project name: the git toplevel's folder name with a
    leading dot dropped (the same rule as lifeview's project_of_root and
    prescient), falling back to the cwd's own folder name outside a repo."""
    root = cwd
    try:
        p = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        if p.returncode == 0 and p.stdout.strip():
            root = p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return os.path.basename(root.rstrip("/")).lstrip(".") or "-"


def sender_tag(from_role: str | None, pane_id: str | None, agents: list[dict],
               cwd: str | None = None, project=project_of) -> tuple[str | None, str]:
    """(the tag line, or None to send untagged; why). The sender is the
    pane this process runs in ($HERDR_PANE_ID), found in `herdr agent list`
    the same way the target is."""
    me = next((a for a in agents if pane_id and a.get("pane_id") == pane_id), None)
    role = from_role or ROLE_OF_KIND.get((me or {}).get("agent") or "")
    if not role:
        if me is None:
            return None, "no herdr agent in this pane ($HERDR_PANE_ID) and no --from"
        return None, f"a {me.get('agent')!r} pane has no default role; pass --from"
    where = (me or {}).get("cwd") or cwd or os.getcwd()
    ident = (me or {}).get("name") or pane_id or "cli"
    return f"[from:{role} project:{project(where)} id:{ident}]", "tagged"


def tagged(text: str, tag: str | None) -> str:
    """The text as sent: the tag on its own first line -- unless the caller
    already supplied one (never double-tag) or there is no tag."""
    if tag is None or ALREADY_TAGGED.match(text):
        return text
    return tag + "\n" + text


# omp's input-frame header line: the frame's top border carrying the model /
# Prewalk ("╭──  Opus 5  main …──╮"). Anchored to the border because a bare
# model name also shows in the welcome banner of a scrolled-back float.
# Case-insensitive: the header writes model ids in lowercase too
# (glm-5.3-flash once prewalk switches to the smol role).
REPL_MARKERS = re.compile(r"╭──[^\n╮]*(Prewalk|Opus|Sonnet|GLM|π)", re.I)
# The input box's bottom border. Accepted only after nvim RPC confirmed the
# REPL focused in terminal mode: omp can redraw the box without its header
# row (seen live 2026-10-26 in a narrowed float: two bottom borders, no top).
INPUT_BOX = re.compile(r"╰─ {2,}[^\n]*─╯")


def repl_visible(pane_id: str, rpc_focused: bool = False) -> bool:
    # The whole visible screen: yarepl's float sits mid-pane, so its input
    # frame can land above any fixed bottom window (missed by one line
    # with --lines 10, seen live 2026-10-26).
    rc, out, _ = herdr("agent", "read", pane_id, "--source", "visible")
    if rc != 0:
        return False
    return bool(REPL_MARKERS.search(out or "") or (rpc_focused and INPUT_BOX.search(out or "")))


# nvim RPC focus -- same machinery as agent-discord's relay
# (config/herdr/plugins/agent-discord/bot.py), kept inline because omp-peer
# is installed as a standalone copy. Every call has a deadline: a modal nvim
# (hit-enter prompt) never answers --remote-expr.
NVIM_RPC_TIMEOUT = 5

# Show + focus the live "pi" REPL and enter terminal mode (which also jumps
# a scrolled-back terminal to its live end) -- what the user's ctrl+a
# (mappings.lua toggle_repl) drives, minus the toggle: idempotent, never
# hides, never starts a REPL. Returns "ok:<bufnr>" or a reason.
_FOCUS_LUA = (
    "(function()"
    " local ok, y = pcall(require, 'yarepl')"
    " if not ok then return 'yarepl not loaded' end"
    " local repl = y._get_repl(0, 'pi', vim.api.nvim_get_current_buf())"
    " if not repl then return 'no pi REPL in this nvim' end"
    " local job = vim.b[repl.bufnr].terminal_job_id"
    " if type(job) ~= 'number' or vim.fn.jobwait({job}, 0)[1] ~= -1 then return 'the pi REPL has exited' end"
    " local win = vim.fn.bufwinid(repl.bufnr)"
    " if win ~= -1 then vim.api.nvim_set_current_win(win)"
    " else y.commands.focus({args = 'pi', count = 0}) end"
    " if vim.api.nvim_get_current_buf() ~= repl.bufnr then return 'could not focus the pi REPL' end"
    " vim.cmd('startinsert')"
    " return 'ok:' .. repl.bufnr"
    " end)()"
)


def nvim_rpc(sock: str, lua: str) -> str | None:
    expr = "luaeval('" + lua.replace("'", "''") + "')"
    try:
        p = subprocess.run(["nvim", "--server", sock, "--remote-expr", expr],
                           capture_output=True, text=True, timeout=NVIM_RPC_TIMEOUT,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout.strip() if p.returncode == 0 and not p.stderr.strip() else None


def pane_nvim_sockets(pane_id: str) -> list[str]:
    """Sockets of the nvim processes under the pane's shell, looked up in
    nvim's stdpath('run') ($XDG_RUNTIME_DIR or $TMPDIR, /nvim.$USER/)."""
    rc, out, _ = herdr("pane", "process-info", "--pane", pane_id)
    try:
        shell = json.loads(out)["result"]["process_info"]["shell_pid"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    if rc != 0 or not shell:
        return []
    ps = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True).stdout
    children: dict[int, list[tuple[int, str]]] = {}
    for line in ps.splitlines():
        f = line.split(None, 2)
        if len(f) == 3 and f[0].isdigit() and f[1].isdigit():
            children.setdefault(int(f[1]), []).append((int(f[0]), f[2]))
    nvims, todo = [], [int(shell)]
    while todo:
        for pid, comm in children.get(todo.pop(), []):
            if os.path.basename(comm.strip()) == "nvim":
                nvims.append(pid)
            todo.append(pid)
    user = os.environ.get("USER") or HOME.name
    roots = {os.environ.get("XDG_RUNTIME_DIR"), os.environ.get("TMPDIR")}
    socks = []
    for r in filter(None, roots):
        for pid in nvims:
            socks += sorted(str(x) for x in (Path(r) / f"nvim.{user}").glob(f"*/nvim.{pid}.*") if x.is_socket())
    return socks


def focus_repl_via_rpc(pane_id: str) -> str:
    """"ok" once nvim reports the REPL buffer current in terminal mode;
    "unavailable" when no nvim socket answers (caller falls back to ctrl+a);
    anything else is nvim's refusal reason."""
    for sock in pane_nvim_sockets(pane_id):
        if nvim_rpc(sock, "1") != "1":
            continue  # stale socket or modal nvim
        res = nvim_rpc(sock, _FOCUS_LUA)
        if res is None:
            return "unavailable"
        if not res.startswith("ok:"):
            return res
        # startinsert lands after the RPC returns; in a terminal buffer's
        # NORMAL mode typed text would run as commands, so confirm first.
        want, state = "t:" + res[3:], None
        for _ in range(10):
            time.sleep(0.1)
            state = nvim_rpc(sock, "vim.api.nvim_get_mode().mode .. ':' .. vim.api.nvim_get_current_buf()")
            if state == want:
                return "ok"
            if state is None:
                return "unavailable"
        return f"the REPL did not reach terminal mode (nvim at {state})"
    return "unavailable"


def ensure_repl_visible(pane_id: str) -> None:
    """Guard for REPL-nested peers (omp inside nvim): raw typing lands in
    whatever pane window has focus, so the omp input box must be visible
    before sending. RPC first (focus_repl_via_rpc): works in any nvim mode
    and jumps a scrolled-back float to its live end. The user's ctrl+a
    cannot: it is mapped in normal+terminal mode only, so with the editor
    in INSERT mode it is i_CTRL-A and does nothing. The ctrl+a double
    toggle (open-but-unfocused hides on the first, reopens on the second;
    verified live 2026-09-05) stays as the fallback when no nvim socket
    answers. Refuses rather than type blind."""
    focus = focus_repl_via_rpc(pane_id)
    if focus == "ok":
        if repl_visible(pane_id, rpc_focused=True):
            return
        print("omp-peer: REPL focused via nvim RPC but its input frame is not on screen; refusing to type blind", file=sys.stderr)
        sys.exit(4)
    if focus != "unavailable":
        print(f"omp-peer: nvim answered RPC but {focus}; refusing to type blind", file=sys.stderr)
        sys.exit(4)
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


def find_claude_transcript(session_id: str | None) -> Path | None:
    """A claude pane's transcript: <dir>/<session-id>.jsonl under CLAUDE_PROJECTS,
    found by the session id herdr reports (agent_session.value), so the
    project-dir naming never has to be re-derived."""
    if not session_id:
        return None
    hits = sorted(CLAUDE_PROJECTS.glob(f"*/{session_id}.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def transcript_locator(target: dict):
    """() -> Path | None for the target's live transcript."""
    if target.get("agent") == "claude":
        sid = (target.get("agent_session") or {}).get("value")
        return lambda: find_claude_transcript(sid)
    cwd = target["cwd"]
    return lambda: find_session_file(cwd)


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
    if e.get("type") == "queue-operation":   # claude: typed while it was busy
        return str(e.get("content") or "")
    msg = e.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):             # claude writes a plain prompt as a string
        return content
    if not isinstance(content, list):
        return ""
    return " ".join(
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
    )


def wait_for(
    label: str,
    locate,  # () -> Path | None: the target's live transcript
    timeout: float,
    match,  # (entries, start_idx) -> int | None
    start: int | None = None,
) -> tuple[Path, int]:
    """Poll the newest session file for `match` over fresh entries only
    (entries from index `start` on, default: those written after the call).
    Returns (file, matched_index)."""
    deadline = time.monotonic() + timeout
    tracked: Path | None = locate()
    baseline = start if start is not None else (len(entries_of(tracked)) if tracked else 0)
    print(f"omp-peer: waiting for {label} (timeout {timeout:.0f}s) ...", file=sys.stderr)
    while time.monotonic() < deadline:
        current = locate()
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
    sp.add_argument("--from", dest="from_role", choices=ROLES,
                    help="sender role for the tag (default: coordinator from an omp pane, worker from a claude pane)")
    sp.add_argument("--dry-run", action="store_true",
                    help="print the text as it would be sent (tag included) and send nothing")
    args = ap.parse_args()

    body = args.text
    tag, why = sender_tag(args.from_role, os.environ.get("HERDR_PANE_ID"), herdr_agents())
    if tag is None and not ALREADY_TAGGED.match(body):
        print(f"omp-peer: sending UNTAGGED ({why}) -- the receiver will guess the sender from the text", file=sys.stderr)
    text = tagged(body, tag)
    if args.dry_run:
        print(text)
        return

    target = agent_info(args.target)
    pane_id = target["pane_id"]
    locate = transcript_locator(target)
    # The baseline is taken BEFORE sending: a claude pane writes its entry
    # (a queue entry when busy) the instant it is typed, which a baseline
    # taken after the send would count as old and never match.
    before = locate()
    baseline = len(entries_of(before)) if before else 0

    rc, out, err = herdr("agent", "prompt", args.target, text)
    raw = False
    if rc != 0:
        if "agent_not_ready" in (err or "") + (out or ""):
            # REPL-nested peer (omp inside nvim): herdr refuses because the
            # pane foreground is nvim, not the agent. Deliver raw, bot-style.
            raw = True
            print("omp-peer: agent prompt refused (nested REPL) -- raw pane delivery", file=sys.stderr)
            if not args.no_guard:
                ensure_repl_visible(pane_id)
            payload = "\x1b[200~" + text + "\x1b[201~"
            rc2, _, err2 = herdr("pane", "send-text", pane_id, payload)
            if rc2 != 0:
                print(f"omp-peer: pane send-text failed: {(err2 or '').strip()}", file=sys.stderr)
                sys.exit(1)
            time.sleep(0.3)
            herdr("pane", "send-keys", pane_id, "enter")
        else:
            print(f"omp-peer: agent prompt failed: {(err or out).strip()}", file=sys.stderr)
            sys.exit(1)

    # From the body, never the tag: the tag is the same on every message
    # this sender sends, so it would match an earlier one.
    # (A caller-supplied tag is skipped the same way.)
    needle_src = re.sub(r"^\s*\[from:[^\]]*\]\s*", "", body) or body
    needle = re.sub(r"\s+", " ", needle_src.strip())[:24]

    def is_delivery(entries: list[dict], start: int) -> int | None:
        for i in range(start, len(entries)):
            e = entries[i]
            msg = e.get("message") or {}
            queued = e.get("type") == "queue-operation" and e.get("operation") == "enqueue"
            if (msg.get("role") == "user" or queued) and needle in re.sub(r"\s+", " ", entry_text(e)):
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
        sfile, idx = wait_for("delivery", locate, args.confirm_timeout, is_delivery, start=baseline)
    except SystemExit as exc:
        if exc.code == 2 and raw:
            # the first Enter can be dropped right after a paste block -- send one more, then judge
            print("omp-peer: retrying enter", file=sys.stderr)
            herdr("pane", "send-keys", pane_id, "enter")
            sfile, idx = wait_for("delivery", locate, args.confirm_timeout, is_delivery, start=baseline)
        else:
            raise
    print(f"delivered {sfile}", file=sys.stderr)

    if not args.wait_reply:
        print(f"delivered {sfile}")
        return

    # Scan from just after the delivered message, not from "now": a fast
    # reply is already in the file by the time this wait starts (seen
    # live 2026-10-26: answered 2.4s after delivery, skipped, exit 3).
    rfile, ridx = wait_for("reply", locate, args.reply_timeout, is_reply, start=idx + 1)
    entries = entries_of(rfile)
    print(entry_text(entries[ridx]).strip())


if __name__ == "__main__":
    main()
