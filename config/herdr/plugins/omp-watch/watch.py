#!/usr/bin/env python3
"""Report omp agent state to herdr using process presence + its own transcript.

Why this exists: omp's extension/hook API -- the mechanism herdr's official
omp integration relies on -- does not deliver a single lifecycle event to
file-discovered extensions in the CLI's interactive mode. Verified
empirically: neither herdr's real integration nor a minimal test extension
(bare `api.on("agent_start", ...)`) ever fired through a live agent turn with
a real model call. herdr also ships no screen-manifest fallback for omp
(unlike Pi/Kimi/OpenCode/Kilo) -- confirmed via
`herdr agent explain --agent omp`, which always returns
`evaluated_rules: []` regardless of what's on screen.

Two signals that work regardless of either broken path:

1. Process presence: a live `omp` process whose resolved cwd matches a
   pane's cwd means the agent is genuinely there -- independent of whether
   the yarepl REPL float is visible, and independent of whether it has ever
   written anything (a freshly opened, never-used REPL has NO transcript
   activity at all; presence is the only way to know it exists).
2. Transcript refinement: omp appends structured JSON Lines to its own
   session file (~/.omp/agent/sessions/<cwd>/<ts>_<uuid>.jsonl) in real time.
   The LAST recognizable entry tells whether the current turn is finished
   (idle) or not (working): an unfinished-turn entry means "working" even
   if the model has been thinking silently for a while, and a
   stale-but-still-open REPL's last entry is simply whatever it left off
   at. One ambiguity is time-gated (IDLE_GRACE_SECONDS): a text-only
   assistant message looks finished, but omp's loop machinery routinely
   CONTINUES the turn after exactly such interim answers (prewalk-
   continue, plan approvals, async subagent results) -- 109 confirmed
   continuations vs 861 genuine ends across all local transcripts, with
   NO per-entry field distinguishing the two (same keys, stopReason
   "stop" on both). The continuation lands p50 12.7s / p90 42s after the
   interim text, so that tail is held "working" until the transcript goes
   quiet -- quiet measured from the newest recognizable entry's own
   timestamp (see IDLE_GRACE_SECONDS for why that is not the file mtime).

Reports via the documented custom-integration CLI pattern:
https://herdr.dev/docs/integrations/#integrate-your-own-agent

Honest scope: there is no reliable "needs your approval" (blocked) signal in
the transcript -- approval prompts are UI-only and are not logged. This
reports working/idle only. Revisit if a future omp version logs approval
events.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

POLL_SECONDS = 3
# How long a session file must stay silent after a text-only assistant
# message (no embedded toolCall -- looks finished) before that idle is
# trusted. omp's loop machinery continues the turn after exactly such
# interim answers (prewalk-continue, plan approvals, async subagent
# results); measured across all local transcripts (109 continuations vs
# 861 genuine ends), the continuation lands p50 12.7s / p90 42s / max
# 259s after the interim text, and the interim entry is indistinguishable
# from a genuine final (same keys, stopReason "stop" on both). 45s covers
# ~90% of continuations outright; the rest self-correct the moment the
# continuation lands, because any newer RECOGNIZABLE entry (toolCall,
# user message, toolResult) re-opens the verdict to "working" immediately.
# The quiet clock is keyed to the NEWEST RECOGNIZABLE ENTRY'S OWN
# timestamp, never the file mtime: harness background machinery appends
# UNrecognizable entries long after the turn ended (subagent-check-in
# nudges, anti-dither/mid-run-todo nudges, model_change records --
# confirmed live 2026-09-24 on w8:p1, whose transcript kept receiving
# custom_message/model_change appends for hours after the final
# assistant message). Keying on mtime made every such append reset the
# 45s window: verdict flipped back to "working", expired to "idle" again
# ~45s later, and each cycle re-fired the working->idle transition that
# agent-discord's notify hook turns into a repeated "done" ping (five
# pings for one turn, each exactly 45s after an append). Unrecognizable
# entries carry no verdict signal, so they must not carry a wake signal
# either.
IDLE_GRACE_SECONDS = 45
# Daemon mode (--daemon): consecutive all-failing ticks before the watcher
# concludes the herdr server itself is gone and exits cleanly, freeing the
# singleton lock for the next server start's [[startup]] instance. Without
# this a daemonized watcher would hold the lock forever after a server
# death and permanently block its replacement.
SERVER_DEATH_TICKS = 10
# How herdr's agent registry is kept honest. Confirmed live 2026-09-05
# (w5:p8, the heinzel-haus pane): reports from OUR source can silently
# stop applying -- exit 0, no error body, registry state frozen -- while
# the SAME source keeps working for other panes, and a ONE-OFF report
# from a never-before-used source name lands instantly and fixes the
# sidebar. The drop persisted for 25+ minutes of 3s-interval resends, so
# resending alone cannot recover. Therefore: every tick cross-checks the
# agent registry (`herdr agent list` -- what the sidebar actually
# renders, NOT the pane-layer agent_status, which can agree while the
# registry is wedged); after ROTATE_AFTER_SENDS consecutive sends that
# fail to converge the registry, the pane's reports move to a fresh
# source name (proven to land immediately). Bounded by
# MAX_ROTATIONS_WITHOUT_CONVERGENCE + a cooldown so a pathological pane
# cannot spam unbounded source names.
ROTATE_AFTER_SENDS = 4
MAX_ROTATIONS_WITHOUT_CONVERGENCE = 3
ROTATION_COOLDOWN_SECONDS = 120
SOURCE = "custom:omp-watch"
AGENT = "omp"
HOME = Path.home()
SESSIONS_DIR = HOME / ".omp" / "agent" / "sessions"
# Plugins should call herdr through HERDR_BIN_PATH, not a bare "herdr" on
# PATH: https://herdr.dev/docs/plugins/
HERDR_BIN = os.environ.get("HERDR_BIN_PATH", "herdr")
# A machine-wide lock, not per-launcher: this same watch.py can plausibly be
# started more than once independently -- by herdr's own [[startup]] hook,
# by a manually-launched interim/debug copy, or by a *different* agent
# session sharing this same repo and machine, entirely unaware of the
# other. Confirmed empirically 2026-09-04: two concurrent reporters both
# using the same hardcoded --source raced on --seq, and one side's report
# would return a clean "ok" yet never actually apply -- indistinguishable
# from a real herdr-side bug until traced to a second process. A single
# machine-wide lock file makes concurrent instances structurally
# impossible, no matter who launches the second one or why.
LOCK_PATH = Path("/tmp/omp-watch.lock")
# Module-level, deliberately: acquire_singleton_lock() must keep this
# reference alive for the whole process lifetime. A local variable would
# be garbage-collected the instant the function returns (CPython reference
# counting is immediate), which closes the fd and releases the flock
# within microseconds of acquiring it -- confirmed empirically 2026-09-04:
# a first-then-second-instance test showed the second instance "wrongly"
# acquiring the lock, because the first had already silently lost it.
_lock_handle: Optional[object] = None


def acquire_singleton_lock() -> None:
    """Exit immediately (not a crash -- a normal, expected outcome) if
    another instance already holds the lock. The handle is intentionally
    never closed: the OS releases the lock the moment this process exits,
    by any means, and holding it open for the process's entire lifetime is
    exactly the point."""
    global _lock_handle
    _lock_handle = open(LOCK_PATH, "w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            f"[omp-watch] another instance already holds {LOCK_PATH} -- exiting, not duplicating it",
            file=sys.stderr,
        )
        sys.exit(0)
    _lock_handle.write(str(os.getpid()))
    _lock_handle.flush()


def session_key(cwd: str) -> str:
    """Mirror scripts/projects/omp-last's cwd -> session-dir-name transform."""
    home_str = str(HOME)
    suffix = cwd[len(home_str):] if cwd.startswith(home_str) else cwd
    return suffix.replace("/", "-")


def newest_session_file(cwd: str) -> Optional[Path]:
    key = session_key(cwd)
    if not key:
        return None
    # omp's dir naming, fully mapped against all six live dirs 2026-09-06:
    # HOME-relative cwds keep their leading slash (/.dotfiles -> -.dotfiles)
    # -- that IS session_key -- while absolute cwds outside HOME are
    # dash-wrapped on BOTH ends (/private/tmp/x -> --private-tmp-x--), so
    # the plain key never matched them and transcript verdicts (working /
    # blocked / maybe_idle) silently never applied to non-HOME agents.
    # Found live when a /tmp-cwd test agent's 404 error tail stayed
    # invisible to the blocked-state pipeline.
    if cwd.startswith(str(HOME)):
        candidates = [key]
    else:
        candidates = ["--" + cwd.strip("/").replace("/", "-") + "--", key]
    for k in candidates:
        d = SESSIONS_DIR / k
        if d.is_dir():
            files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            if files:
                return files[0]
    return None


_ver_cache: Dict[str, Tuple[int, Optional[str], bytes]] = {}
SCAN_CHUNK_BYTES = 2 * 1024 * 1024
CARRY_BYTES = 64


def config_version(path: Path) -> Optional[str]:
    """The RUNNING agent's harness config version, or None.

    omp-config-version.ts appends a custom_message entry ("config v<N>")
    at every process start. Sessions RESUME into the same jsonl (the
    user's REPL flow), so on a resumed transcript the newest entry sits
    near the tail of a multi-MB file -- a head-only scan never sees it.
    Newest match wins by design: a resumed process is a new agent start,
    and its snapshot is the running version. Scanned INCREMENTALLY: a
    per-file (consumed-offset, version, carry) cache forward-reads at
    most SCAN_CHUNK_BYTES of new bytes per call, so quiet multi-MB
    transcripts cost nothing and active ones catch up within a few
    ticks. A shrunken file (fresh/truncated session) resets the scan.
    Matches are raw substring finds, NOT line-gated: an entry can span a
    chunk boundary (customType in one chunk, the version digits in the
    next), so the last CARRY_BYTES ride along to stitch the seam -- the
    same seam failure class the fan-out guards exist for.
    """
    key = str(path)
    try:
        fsize = path.stat().st_size
    except OSError:
        return _ver_cache.pop(key, (0, None, b""))[1]
    offset, ver, carry = _ver_cache.get(key, (0, None, b""))
    if fsize < offset:
        offset, ver, carry = 0, None, b""
    if offset >= fsize:
        return ver
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            chunk = f.read(min(fsize - offset, SCAN_CHUNK_BYTES))
    except OSError:
        return ver
    data = carry + chunk
    new_offset = offset + len(chunk)
    for line in data.split(b"\n"):
        if b"config-version" not in line:
            continue
        # Structural check, not substring: the line must PARSE as the actual
        # injected entry (custom_message/config-version). Conversation text
        # quoting "config v23" lives inside message entries whose parse
        # yields type=message -- skipped. Seam-split partial lines fail to
        # parse -- skipped; the carry makes the complete line available in
        # the next chunk.
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if (
            not isinstance(entry, dict)
            or entry.get("type") != "custom"
            or entry.get("customType") != "dotfiles.config-version"
        ):
            continue
        data_ver = (entry.get("data") or {}).get("version")
        if data_ver:
            ver = str(data_ver)
    carry = chunk[-CARRY_BYTES:] if len(chunk) >= CARRY_BYTES else carry + chunk
    _ver_cache[key] = (new_offset, ver, carry)
    return ver


def classify_entry(e: dict) -> Optional[str]:
    """Recognize a single transcript entry and return its verdict
    contribution: "working", "maybe_idle", "blocked", "exit", or None for entries
    that carry no signal (unrecognized entries are conservative: they
    never change a running verdict)."""
    etype = e.get("type")
    # role lives at entry.message.role, not top-level -- confirmed
    # empirically 2026-09-04 against a real session file; the earlier
    # top-level e.get("role") always returned None, so the user/
    # assistant/toolResult branches below never actually matched.
    msg = e.get("message") or {}
    role = msg.get("role")
    if etype == "custom" and e.get("customType") == "session_exit":
        return "exit"
    if etype == "custom" and e.get("customType") == "tool_execution_start":
        return "working"
    if etype in ("toolCall", "function_call"):
        return "working"
    if etype == "message" and role == "user":
        return "working"
    if etype == "message" and role == "toolResult":
        return "working"  # the agent loop still has to react to it
    if etype == "message" and role == "assistant":
        # An assistant message's role alone does NOT mean the turn is
        # done -- confirmed empirically 2026-09-04 against ~444 real
        # assistant entries: a toolCall block can be embedded directly
        # in the SAME message (Anthropic-style), atomically, alongside
        # thinking and/or text (221 text+thinking+toolCall, 127
        # thinking+toolCall, 39 toolCall-only, 7 text+toolCall -- all
        # genuinely still working despite having a "text" block).
        # Racing on a LATER separate tool_execution_start event was the
        # bug: this reads the decision straight out of the one entry
        # that already carries it, so there is nothing left to race.
        # Text with NO toolCall is NOT automatically a finished turn
        # either (the earlier "text-only = finished" conclusion was
        # wrong): omp's loop machinery continues the turn after
        # exactly such interim answers -- prewalk-continue, plan
        # approvals, async subagent results; 109 confirmed
        # continuations vs 861 genuine ends across all local
        # transcripts, with NO per-entry field distinguishing the two
        # (same keys, stopReason "stop" on both). Returned as
        # "maybe_idle" so main() can hold it working until the transcript
        # goes quiet (IDLE_GRACE_SECONDS, measured from the newest
        # recognizable entry's own timestamp, not the file mtime).
        # Thinking-only/empty
        # content still means reasoning, not yet answered.
        # stopReason is the turn's exit status and outranks content shape:
        # "error" is a DEAD turn -- model/provider failure (verified live
        # 2026-09-06: OpenRouter guardrail 404s land as assistant entries
        # with content [] + stopReason "error" + errorStatus/errorMessage).
        # Reported as herdr "blocked": the sidebar flags it and notify.py
        # pings Discord on the working->blocked transition. Without this
        # the empty-content fallthrough below pinned failed agents at
        # "working" forever -- the file never gets another byte.
        # "aborted" ("Interrupted by user") is NOT a failure: the turn
        # ended without failing, the agent waits for input -- same shape
        # as a completed text turn.
        stop = msg.get("stopReason")
        if stop == "error":
            return "blocked"
        if stop == "aborted":
            return "maybe_idle"
        content = msg.get("content") or []
        has_tool_call = any(isinstance(c, dict) and c.get("type") == "toolCall" for c in content)
        has_text = any(isinstance(c, dict) and c.get("type") == "text" for c in content)
        if has_tool_call:
            return "working"
        if has_text:
            return "maybe_idle"
        return "working"
    return None


def infer_state(entries: List[dict]) -> Optional[str]:
    """Walk entries oldest->newest; the LAST recognizable entry decides.
    Kept as the list-based form of latest_verdict() for tests and
    one-off replays. The ambiguous text-only-assistant tail returns
    "maybe_idle" rather than "idle"; main() gates that on signal
    quiescence (IDLE_GRACE_SECONDS) before reporting idle to herdr."""
    verdict: Optional[str] = None
    for e in entries:
        v = classify_entry(e)
        if v is not None:
            verdict = v
    return verdict


def _entry_epoch(e: dict) -> Optional[float]:
    """Wall-clock epoch of an entry's own "timestamp" field, or None.
    omp timestamps are ISO-8601 with a trailing Z; parsed here so the
    idle-grace clock can run on signal age instead of file mtime."""
    ts = e.get("timestamp")
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def latest_verdict(
    path: Path, max_bytes: int = 8 * 1024 * 1024, max_parsed: int = 4000
) -> Tuple[Optional[str], Optional[float]]:
    """(verdict, tail_epoch) of the newest COMPLETE recognizable entry,
    scanning the file backwards from EOF. Replaced a fixed 32KB tail window
    after it collapsed to "no recognizable entries -> default idle" whenever
    the newest entry was bigger than the window: seek(size - 32KB) lands
    mid-line, readline() discards everything to EOF, and a heinzel-
    exploration-sized agent (40-60KB toolResult/assistant entries from
    big file reads, back to back) left the window empty for ~100s of
    active work on 2026-09-05 -- a false "done" the user watched live.
    This scanner has no per-entry size assumption: only newline-
    terminated lines are considered (a missing final newline = writer
    mid-flush = skip, never mis-parse), unparseable lines are skipped,
    and the scan stops at the first recognizable entry -- exactly
    infer_state's "last recognizable entry wins" semantics, made robust
    to any entry size. Budget-bounded; exhausting it returns (None, None),
    which main() treats like any other unrecognizable tail. tail_epoch is
    the newest recognizable entry's OWN timestamp (see the
    IDLE_GRACE_SECONDS block for why that must not be the file mtime);
    None when the entry carries no parseable timestamp."""
    size = path.stat().st_size
    pos = size
    carry = b""  # head-fragment of a line whose tail was already scanned
    scanned = 0
    parsed = 0
    with path.open("rb") as f:
        # The file's final line is only complete if a newline terminates
        # it; otherwise the writer is mid-flush and that fragment is
        # skipped exactly like any other partial line.
        f.seek(size - 1) if size else None
        final_terminated = size > 0 and f.read(1) == b"\n"
        first_chunk = True
        while pos > 0 and scanned < max_bytes and parsed < max_parsed:
            chunk_size = min(65536, pos, max_bytes - scanned)
            pos -= chunk_size
            f.seek(pos)
            data = f.read(chunk_size) + carry
            scanned += chunk_size
            parts = data.split(b"\n")
            carry = parts[0]
            lines = parts[1:]
            if first_chunk:
                first_chunk = False
                if not final_terminated and lines:
                    lines = lines[:-1]  # newest fragment is not a complete line
            for ln in reversed(lines):
                s = ln.strip()
                if not s:
                    continue
                try:
                    e = json.loads(s)
                except Exception:
                    continue  # partial or malformed line -- keep scanning back
                parsed += 1
                v = classify_entry(e)
                if v is not None:
                    return v, _entry_epoch(e)
    return None, None


def process_cwd(pid: int) -> Optional[str]:
    proc_cwd = Path(f"/proc/{pid}/cwd")
    if proc_cwd.exists():
        try:
            return str(proc_cwd.resolve())
        except OSError:
            return None
    # macOS / BSD: no /proc, resolve via lsof instead.
    try:
        out = subprocess.run(
            ["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in out.stdout.splitlines():
            if line.startswith("n"):
                return line[1:]
    except Exception:
        pass
    return None


def live_omp_pids() -> Tuple[Dict[int, int], Dict[int, int]]:
    """(omp_pids, all_ppids): omp_pids maps {pid: ppid} for every running omp
    process matched by resolved argv
    basename (covers both a direct `omp ...` invocation and the
    `bun .../bin/omp ...` shape this machine actually uses).

    v0.9.0 rework: attribution is PID-BASED, not cwd-based. The previous
    live_omp_cwds() built {cwd: pid} and main() credited every pane whose
    cwd matched a live omp process, so a claude/plain-shell pane in the
    SAME repo as an nvim+omp REPL was mis-reported as omp every tick
    (observed live 2026-09-15 on thor-voiceai: a new pane in that cwd
    showed agent=omp regardless of its actual occupant). tty-only
    matching is insufficient too: an omp nested in an nvim REPL runs on
    nvim's internal pty, not the pane's tty. The robust link is
    ANCESTRY: an omp process's ppid chain terminates exactly at the pane
    shell (ps -o ppid, bounded walk; verified live -- omp ->
    nvim --embed -> nvim -> pane shell). main() matches a pane by
    pane-shell-pid in the omp process's ancestor set; no cwd involved.
    """
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True, timeout=10
    )
    ppids: Dict[int, int] = {}
    omp_pids: List[int] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_str, _, rest = line.partition(" ")
        rest = rest.strip()
        ppid_str, _, cmd = rest.partition(" ")
        try:
            pid = int(pid_str)
            ppid = int(ppid_str)
        except ValueError:
            continue
        ppids[pid] = ppid
        tokens = cmd.split()
        if any(Path(t).name == "omp" for t in tokens if not t.startswith("-")):
            omp_pids.append(pid)
    # the FULL ppid table is required for ancestry walks: an omp nested in
    # wrappers (bash -> nvim -> pty -> omp) crosses several non-omp
    # processes before reaching the pane shell, and a table of only omp
    # pids would stop the walk after one hop (the exact bug that left the
    # freshly-recreated pane unattributed, 2026-09-15).
    return {pid: ppids[pid] for pid in omp_pids}, ppids


def ancestor_set(omp_pids: Dict[int, int], ppids: Dict[int, int]) -> Dict[int, set]:
    """{omp_pid: {self + every ancestor pid}} via one bounded ppid walk per
    process over the FULL process table (ppids covers every process, not
    just omp ones -- see live_omp_pids). Bounded at 32 levels; unknown ppid
    entries terminate the walk defensively."""
    chains: Dict[int, set] = {}
    for pid in omp_pids:
        chain = {pid}
        p = omp_pids[pid]
        depth = 0
        while p is not None and p > 1 and depth < 32:
            chain.add(p)
            nxt = ppids.get(p)
            if nxt is None:
                break
            p = nxt
            depth += 1
        chains[pid] = chain
    return chains


def pane_shell_pids(pane_ids: List[str]) -> Dict[str, Optional[int]]:
    """{pane_id: shell_pid} via `herdr pane process-info` (one call per
    pane; measured ~0.2s for all 8 panes). Failed lookups -> None: the
    pane is treated as omp-less (never falsely omp)."""
    result: Dict[str, Optional[int]] = {}
    for pane_id in pane_ids:
        try:
            out = subprocess.run(
                [HERDR_BIN, "pane", "process-info", "--pane", pane_id],
                capture_output=True, text=True, timeout=10,
            )
            info = json.loads(out.stdout)["result"]["process_info"]
            result[pane_id] = info.get("shell_pid")
        except Exception:
            result[pane_id] = None
    return result


def run_herdr(*args: str) -> bool:
    """Run a herdr CLI call and report whether it actually succeeded --
    callers must not cache a new last-reported state unless this is True,
    or a transient CLI/socket failure gets silently treated as delivered
    and never retried until some unrelated later state change happens to
    paper over it (a real, if unconfirmed, suspect behind one report of
    a stuck "working" state 2026-09-04)."""
    try:
        result = subprocess.run(
            [HERDR_BIN, *args], check=False, capture_output=True, text=True, timeout=10
        )
    except Exception as exc:  # keep the watcher alive across any CLI hiccup
        print(f"[omp-watch] herdr call failed {args}: {exc}", file=sys.stderr)
        return False
    if result.returncode != 0:
        print(f"[omp-watch] herdr call exited {result.returncode} {args}: {result.stderr.strip()}", file=sys.stderr)
        return False
    # herdr's socket API can return exit 0 with an application-level
    # {"error": {...}} body; treat that as failure too rather than a
    # false-positive success.
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {}
    if isinstance(parsed, dict) and "error" in parsed:
        print(f"[omp-watch] herdr call returned an error {args}: {parsed['error']}", file=sys.stderr)
        return False
    return True


def load_registry() -> Optional[Dict[str, str]]:
    """{pane_id: agent_status} from `herdr agent list` -- the registry the
    sidebar actually renders. Distinct from the pane-layer agent_status
    that load_panes() returns: on 2026-09-05 (w5:p8) the two layers
    disagreed (pane layer showed our reported state, registry sat on the
    default_known_agent_idle_fallback), so only the registry is truth for
    the cross-check. Returns None if the call itself fails, which callers
    must distinguish from an empty dict: None means "no verdict from
    herdr this tick -- skip the cross-check" rather than "everything
    mismatches" (the latter would spam reports during a CLI outage)."""
    try:
        out = subprocess.run(
            [HERDR_BIN, "agent", "list"], capture_output=True, text=True, timeout=10
        )
        agents = json.loads(out.stdout)["result"]["agents"]
        return {a["pane_id"]: (a.get("agent_status"), a.get("name")) for a in agents}
    except Exception as exc:
        print(f"[omp-watch] agent list failed: {exc}", file=sys.stderr)
        return None


def registry_matches(verdict: str, registry_status: Optional[str]) -> bool:
    """Does the registry's rendering of a pane agree with our verdict?
    "done" is herdr's own legitimate rendering of a reported "idle" left
    unviewed. None/unknown is deliberately a MISMATCH even for idle: a
    pane missing from the registry (fresh pane, or a herdr server
    restart wiping it) must be (re-)reported at least once or it never
    appears in the sidebar; herdr dedupes redundant same-state reports,
    so the cost of that rule is one cheap no-op send per pane per
    registry reset, not spam."""
    if verdict == "idle":
        return registry_status in ("idle", "done")
    return registry_status == verdict


def foreign_claim(pane: dict) -> Optional[str]:
    """The source of a FOREIGN agent-session claim on this pane, if any.

    A managed integration's claim (e.g. `herdr:claude`, registered by ANY
    claude process that inherits the pane's HERDR_PANE_ID -- including a
    short `claude -p` probe run from that pane's shell) takes ownership of
    the pane's agent slot. herdr then accepts our report-agent calls with a
    clean "ok" and never applies them: the sidebar freezes at whatever
    state was live when the claim landed. Verified exhaustively
    2026-09-15 on w6:p4 (frozen at "working", state_change_seq 1181):
    reports from our own source AND from never-used fresh sources both
    returned ok and changed nothing; `release-agent` and a no-id
    `report-agent-session` from the owning source are both no-ops; and the
    claim is persisted under .panes[].agent_session in
    ~/.config/herdr/session.json, so it survives server restarts. Nothing
    we send can win, so main() warns once and skips the pane rather than
    burning source rotations on an unwinnable one. Remedies are outside
    this process: recreate the pane, or stop the server and strip the
    claims (scripts/herdr-clear-agent-claims.sh).
    """
    claim = pane.get("agent_session") or {}
    source = claim.get("source") or ""
    if source and not source.startswith(SOURCE):
        return source
    return None


def load_panes() -> List[dict]:
    ws_out = subprocess.run(
        [HERDR_BIN, "workspace", "list"], capture_output=True, text=True, timeout=10
    )
    workspaces = json.loads(ws_out.stdout)["result"]["workspaces"]
    panes: List[dict] = []
    for ws in workspaces:
        pane_out = subprocess.run(
            [HERDR_BIN, "pane", "list", "--workspace", ws["workspace_id"]],
            capture_output=True,
            text=True,
            timeout=10,
        )
        panes.extend(json.loads(pane_out.stdout)["result"]["panes"])
    return panes


DEBUG = os.environ.get("OMP_WATCH_DEBUG") == "1"
DAEMONIZED = False


def dlog(msg: str) -> None:
    if DEBUG:
        print(f"[omp-watch:debug {time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)

_HUP = {"flag": False}


def _on_sighup(signum: int, frame: object) -> None:
    _HUP["flag"] = True


signal.signal(signal.SIGHUP, _on_sighup)


def main() -> None:
    parent_pid_at_start = os.getppid()
    last_state: Dict[str, str] = {}
    tick_errors = 0
    # Per-pane reporting source. Starts as the shared default; a pane
    # whose reports stop converging the registry gets rotated onto a
    # fresh source name (see the constants block + registry_matches --
    # confirmed live 2026-09-05 that a never-used source lands instantly
    # where a wedged (source, pane) pair is silently discarded).
    pane_sources: Dict[str, str] = {}
    # Consecutive sends per pane that did not converge the registry;
    # drives rotation. Rotations done per pane without convergence;
    # cooldown-until timestamps per pane after giving up.
    unconfirmed: Dict[str, int] = {}
    rotations: Dict[str, int] = {}
    cooldown_until: Dict[str, float] = {}
    rotation_counter = 0
    # Panes whose agent slot is owned by a foreign source (see
    # foreign_claim): warned once each, then skipped every tick.
    foreign_claims: Dict[str, str] = {}
    last_seq_sent = 0
    dlog(f"main() starting, pid={os.getpid()} parent_pid={parent_pid_at_start}")

    def next_seq(pane_id: str) -> int:
        # Timestamp-based (ms since epoch), not a small per-process counter
        # starting at 1 -- confirmed empirically 2026-09-04 that a fresh
        # process's low seq (1, 2, 3...) can be silently treated as stale
        # forever relative to a leftover higher value from unrelated
        # earlier manual testing against the same hardcoded --source (a
        # one-off `--seq 999` call while debugging poisoned it for good).
        # A millisecond timestamp is always larger than anything a human
        # would type ad hoc, naturally monotonic across restarts, and
        # needs no persisted per-pane state. `pane_id` is unused now but
        # kept so call sites don't change.
        nonlocal last_seq_sent
        value = max(int(time.time() * 1000), last_seq_sent + 1)
        last_seq_sent = value
        return value

    def release(pane_id: str) -> None:
        if pane_id in last_state:
            src = pane_sources.get(pane_id, SOURCE)
            if run_herdr("pane", "release-agent", pane_id, "--source", src, "--agent", AGENT):
                dlog(f"{pane_id}: released (was {last_state.get(pane_id)!r})")
                last_state.pop(pane_id, None)
                unconfirmed.pop(pane_id, None)
                rotations.pop(pane_id, None)
                cooldown_until.pop(pane_id, None)
                pane_sources.pop(pane_id, None)
            else:
                dlog(f"{pane_id}: release-agent call FAILED, will retry next tick")
            # else: leave it tracked so the next tick retries the release
            # instead of silently treating a failed call as delivered.

    tick = 0
    while True:
        tick += 1
        # herdr's [[startup]] hook has no supervision and sends this
        # process no signal when its owning server shuts down (verified
        # empirically 2026-09-04: three successive server restarts each
        # left a fully orphaned watcher running under init -- multiple
        # instances silently accumulated and fought over the same panes,
        # which is exactly why a newly opened pane in another workspace
        # stayed stuck on "unknown"). A dead parent reparents us; exit for
        # good the instant that happens -- the new server spawns its own
        # fresh instance, and this one must not linger to duplicate it.
        if not DAEMONIZED and os.getppid() != parent_pid_at_start:
            print(
                f"[omp-watch] orphaned (parent {parent_pid_at_start} -> {os.getppid()}); exiting for good",
                file=sys.stderr,
            )
            sys.exit(0)
        if DAEMONIZED and tick_errors >= SERVER_DEATH_TICKS:
            print(
                "[omp-watch] herdr server unreachable for too long -- daemon exiting; "
                "the next server start will spawn a fresh watcher",
                file=sys.stderr,
            )
            sys.exit(0)
        if _HUP["flag"]:
            print("[omp-watch] SIGHUP -> re-exec (code reload)", file=sys.stderr)
            os.execv(sys.executable, [sys.executable, __file__])

        try:
            live, all_ppids = live_omp_pids()
            chains = ancestor_set(live, all_ppids)
            panes = load_panes()
            # One registry read per tick, shared by every pane below.
            # None (call failed) disables the cross-check for this tick.
            registry = load_registry()
            dlog(f"tick {tick}: live_omp_pids={live}")
            dlog(f"tick {tick}: registry={registry}")
            # v0.9.0: attribution = pane shell pid in a live omp's ancestor
            # set (one `pane process-info` sweep per tick; see
            # live_omp_pids() for why ancestry replaced cwd matching).
            shell_pids = pane_shell_pids([p["pane_id"] for p in panes])
            dlog(f"tick {tick}: shell_pids={shell_pids}")
            for pane in panes:
                pane_id = pane["pane_id"]
                cwd_raw = pane.get("cwd", "")

                shell_pid = shell_pids.get(pane_id)
                live_here = shell_pid is not None and any(
                    shell_pid in chains[omp_pid] for omp_pid in chains
                )
                if not live_here:
                    if pane_id in last_state:
                        dlog(f"{pane_id}: no live omp under shell {shell_pid!r} -> releasing")
                    release(pane_id)
                    continue

                # A foreign agent-session claim (e.g. herdr:claude, planted by any
                # claude process that inherited this pane's HERDR_PANE_ID) does NOT
                # by itself stop our reports from applying -- verified 2026-09-15 on
                # w6:pJ, where report-agent landed fine with such a claim present.
                # So NEVER skip or release on sight of one: doing that removed our
                # reports from a pane whose live occupant is omp, and since herdr
                # ships no screen manifest for omp the pane then sat on herdr's
                # "default_known_agent_idle_fallback" -- showing idle while the agent
                # was demonstrably working. The claim only matters when reports also
                # stop converging (the w6:p4 freeze), so it is reported there, as a
                # diagnosis, in the non-convergence path below.
                claimed_by = foreign_claim(pane)

                # Present -> at least idle. Only upgrade to "working" when
                # the transcript's last entry represents an unfinished turn;
                # no file yet (never used) or a finished last entry both
                # mean idle. Unfinished-turn entries hold "working" no
                # matter how long the model thinks silently; the ONLY
                # time-gated path is the ambiguous text-only assistant
                # tail ("maybe_idle"), held working until the transcript has
                # been quiet for IDLE_GRACE_SECONDS (see infer_state --
                # omp's loop continues the turn after interim text-only
                # answers, and any newer recognizable entry flips this
                # back to working; unrecognizable background appends --
                # nudges, model_change -- do not, or every such append
                # would re-fire a working->idle transition and its
                # Discord "done" ping, the 2026-09-24 w8:p1 flap).
                verdict = "idle"
                sfile = newest_session_file(cwd_raw)
                tail_verdict = None
                tail_epoch = None
                quiet = None
                if sfile is not None:
                    tail_verdict, tail_epoch = latest_verdict(sfile)
                    if tail_verdict == "blocked":
                        # Turn-level failure (model/provider error): hold
                        # blocked until the transcript's next entry -- a new
                        # user message flips to working, a successful retry
                        # resolves to its own verdict. No quiescence gate:
                        # an error entry is terminal for its turn.
                        verdict = "blocked"
                    elif tail_verdict == "working":
                        verdict = "working"
                    elif tail_verdict == "maybe_idle":
                        # Signal age, not file age: unrecognized appends
                        # (harness nudges, model_change) bump mtime for
                        # hours after the turn ended without carrying any
                        # verdict signal; keying on mtime re-armed the
                        # grace window on each one. Fall back to mtime only
                        # when the entry itself carries no parseable
                        # timestamp.
                        signal_ts = tail_epoch
                        if signal_ts is None:
                            signal_ts = sfile.stat().st_mtime
                        quiet = time.time() - signal_ts
                        verdict = "working" if quiet < IDLE_GRACE_SECONDS else "idle"
                dlog(
                    f"{pane_id}: cwd={cwd_raw!r} sfile={sfile.name if sfile else None} "
                    f"tail_verdict={tail_verdict!r} verdict={verdict!r} "
                    f"quiet={round(quiet, 1) if quiet is not None else None} "
                    f"last_state={last_state.get(pane_id)!r}"
                )
                # The registry (what the sidebar renders) is the authority
                # for whether our report LANDED -- not run_herdr()'s exit
                # code and not the pane-layer agent_status. Proven live
                # 2026-09-05 (w5:p8): reports can return a clean "OK" yet
                # never apply, the pane layer can even show the intended
                # state while the registry sits on its idle fallback, and
                # 25+ minutes of 3s resends do not recover -- but a single
                # report from a never-used source name lands instantly.
                # So: report on any registry/verdict mismatch; if the
                # mismatch survives ROTATE_AFTER_SENDS consecutive sends,
                # rotate this pane onto a fresh source name; if rotations
                # keep failing too, back off for ROTATION_COOLDOWN_SECONDS
                # instead of spamming sources forever.
                if registry is None:
                    dlog(f"{pane_id}: registry unavailable this tick -- skipping cross-check")
                    continue
                reg_status, reg_name = registry.get(pane_id, (None, None))
                # Harness config version naming (omp-config-version.ts):
                # the transcript records "config v<N>" at session start;
                # name the roster entry "omp-v<N>" so parallel agents on
                # different config versions are distinguishable. Renames
                # only touch our own naming shape (unset/"omp"/omp-v<N>) --
                # a user-given agent name always wins. No recorded version
                # (pre-feature session) keeps the entry unversioned, and a
                # leftover omp-v* name from our own earlier run is cleared.
                desired_name = None
                caught_up = True
                if sfile is not None:
                    ver = config_version(sfile)
                    # caught-up = the incremental scanner has consumed the
                    # whole file. While it is still catching up (fresh
                    # re-exec over a multi-MB transcript), ver=None means
                    # "not scanned yet", NOT "no version": hold the existing
                    # name instead of clearing it, or every re-exec flaps
                    # named panes through --clear for a few ticks.
                    st = _ver_cache.get(str(sfile))
                    if st:
                        caught_up = st[0] >= sfile.stat().st_size
                    if ver:
                        desired_name = f"omp-v{ver}"
                want_rename = None
                if desired_name and reg_name != desired_name and (
                    not reg_name or reg_name == "omp" or re.match(r"^omp-v\d+$", reg_name)
                ):
                    want_rename = desired_name
                # No --clear: clearing on a not-yet-annotated transcript
                # (fresh session before its first run lands the entry)
                # flaps the roster name. A stale omp-v* name on a pane
                # whose transcript predates the feature is cosmetic and
                # self-corrects on the session's next process restart.
                if want_rename:
                    if run_herdr("agent", "rename", pane_id, want_rename):
                        dlog(f"{pane_id}: renamed -> {want_rename!r}")
                if registry_matches(verdict, reg_status):
                    unconfirmed.pop(pane_id, None)
                    rotations.pop(pane_id, None)
                    cooldown_until.pop(pane_id, None)
                    last_state[pane_id] = verdict
                    continue

                now = time.time()
                if now < cooldown_until.get(pane_id, 0):
                    dlog(f"{pane_id}: in rotation cooldown, registry={reg_status!r} verdict={verdict!r}")
                    continue
                if rotations.get(pane_id, 0) >= MAX_ROTATIONS_WITHOUT_CONVERGENCE:
                    print(
                        f"[omp-watch] {pane_id}: registry stuck at {reg_status!r} "
                        f"after {rotations[pane_id]} source rotations -- backing off "
                        f"{ROTATION_COOLDOWN_SECONDS}s",
                        file=sys.stderr,
                    )
                    cooldown_until[pane_id] = now + ROTATION_COOLDOWN_SECONDS
                    rotations[pane_id] = 0
                    unconfirmed[pane_id] = 0
                    continue

                unconfirmed[pane_id] = unconfirmed.get(pane_id, 0) + 1
                if (
                    claimed_by
                    and unconfirmed[pane_id] > ROTATE_AFTER_SENDS
                    and foreign_claims.get(pane_id) != claimed_by
                ):
                    # Reports are not landing AND a foreign integration owns the
                    # pane's agent slot: this is the frozen-pane signature (w6:p4,
                    # 2026-09-15 -- our source, fresh sources, release-agent and a
                    # no-id report-agent-session from the owning source were all
                    # no-ops, and the claim persists in session.json across
                    # restarts). Name it once so the cause is obvious instead of
                    # looking like a watcher bug; keep reporting regardless.
                    foreign_claims[pane_id] = claimed_by
                    claim_agent = (pane.get("agent_session") or {}).get("agent")
                    print(
                        f"[omp-watch] {pane_id}: reports not converging AND agent slot "
                        f"owned by {claimed_by!r} (agent={claim_agent!r}) -- this pane's "
                        f"status is frozen at herdr's end. Recreate the pane, or stop the "
                        f"server and run scripts/herdr-clear-agent-claims.sh.",
                        file=sys.stderr,
                    )
                rotate = unconfirmed[pane_id] > ROTATE_AFTER_SENDS
                if rotate:
                    rotation_counter += 1
                    pane_sources[pane_id] = f"{SOURCE}-r{rotation_counter}"
                    rotations[pane_id] = rotations.get(pane_id, 0) + 1
                    unconfirmed[pane_id] = 1
                    print(
                        f"[omp-watch] {pane_id}: reports not converging registry "
                        f"(registry={reg_status!r}, verdict={verdict!r}) -- rotating source "
                        f"to {pane_sources[pane_id]}",
                        file=sys.stderr,
                    )
                src = pane_sources.get(pane_id, SOURCE)
                seq_value = next_seq(pane_id)
                report_args = [
                    "pane", "report-agent", pane_id,
                    "--source", src, "--agent", AGENT, "--state", verdict,
                    "--seq", str(seq_value),
                ]
                if sfile is not None:
                    report_args += ["--agent-session-path", str(sfile)]
                ok = run_herdr(*report_args)
                dlog(
                    f"{pane_id}: report-agent src={src!r} state={verdict!r} seq={seq_value} "
                    f"-> {'OK' if ok else 'FAILED'} (unconfirmed={unconfirmed[pane_id]}, "
                    f"rotations={rotations.get(pane_id, 0)})"
                )
                if ok:
                    last_state[pane_id] = verdict
                # If the send reached herdr, the next tick's registry check
                # converges and resets the counters; if herdr silently
                # dropped it, the counters keep climbing until rotation.
            tick_errors = 0
        except Exception as exc:  # never let one bad tick kill the watcher
            tick_errors += 1
            print(f"[omp-watch] tick error ({tick_errors} consecutive): {exc}", file=sys.stderr)
            if DEBUG:
                import traceback
                traceback.print_exc(file=sys.stderr)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    # Acquired exactly once per process lifetime, here rather than inside
    # main(): main() can be re-entered by the crash-retry loop below
    # *within the same process*, and re-acquiring a flock from a second
    # freshly-opened file handle would see this process's own still-held
    # first handle as "another instance" and wrongly self-exit.
    # --daemon: double-fork so the watcher detaches from any short-lived
    # launcher (shell, agent bash tool) and reparents to launchd with ppid 1.
    # A bash-launched foreground copy would self-terminate the moment its
    # parent exited (the orphan check is keyed to the spawning parent); a
    # daemonized copy skips that check (DAEMONIZED) and instead exits when
    # the herdr server itself goes away. The double-fork guarantees the
    # surviving grandchild is never a session leader and has ppid 1 from
    # its first tick onward.
    if "--daemon" in sys.argv:
        sys.argv.remove("--daemon")
        if os.fork():
            sys.exit(0)
        os.setsid()
        if os.fork():
            sys.exit(0)
        DAEMONIZED = True
        # Detach stdio to a log file, not /devnull: a silent daemon is
        # undebuggable -- a failed re-exec crash-loops invisibly under the
        # crash-retry net (hit live 2026-09-24).
        log_path = os.environ.get("OMP_WATCH_LOG", "/tmp/omp-watch-daemon.log")
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.dup2(log_fd, 0)
        os.dup2(log_fd, 1)
        os.dup2(log_fd, 2)
        if log_fd > 2:
            os.close(log_fd)
    acquire_singleton_lock()
    # Respawn on an unexpected crash (main()'s own per-tick try/except
    # already handles routine failures, so this is a last-resort net);
    # but a SystemExit from the orphan check above must propagate and
    # actually end the process, not be treated as a crash to recover from.
    while True:
        try:
            main()
        except SystemExit:
            raise
        except Exception as exc:
            print(f"[omp-watch] main() crashed: {exc}; restarting in 1s", file=sys.stderr)
            time.sleep(1)
