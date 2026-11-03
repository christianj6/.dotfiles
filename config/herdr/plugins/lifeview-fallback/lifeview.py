#!/usr/bin/env python3
"""Keep prescient's life-view icons true from the harness, without agents.

The life view shows each agent's state from two sources. This plugin feeds
both, so no agent has to remember a CLI:

1. The inner line comes from <repo>/prescient-status.json. Each tick, herdr's
   own agent_status is written there for every agent that hasn't spoken for
   itself. omp's herdr status is already transcript-backed (omp-watch), and
   claude's comes from its hooks.
2. The ring is green when a bro task is `ready`. When an agent settles after
   working on its one open bro task, the plugin marks that task ready through
   bro's HTTP API, with its last message as the summary and the provenance in
   the note ("auto: " summary prefix). See ready_check() for every
   condition; LIFEVIEW_AUTO_READY=0 turns it off.

Status-file rules (the agent's own word always wins):
- Entries are keyed by pane id, as `prescient status` keys them, so an
  agent's next write replaces ours in place.
- Ours carry "by": "harness" (prescient reads state/line/at and ignores
  other keys) and a "harness: ..." line. Older "by": "fallback" entries count
  as ours too.
- An agent-authored entry is never touched while fresh: younger than
  AGENT_FRESH_S, or within its own ttl_s. Past that, a `working` herdr no
  longer corroborates is replaced (see compatible()), and an idle/standby
  older than LIFEVIEW_STALE_OVERRIDE_S loses to herdr working/blocked when
  the transcript agrees (see stale_override()). An agent's `blocked` is
  never overridden.
- The line of a working/blocked/settling entry is what the transcript says
  the agent is doing (see activity_line()), for the dashboard's hover.
- herdr "unknown" or absent says nothing, so nothing is written for it.
- Ours are removed once the agent has its own entry under its name, or
  once its pane is gone from herdr.
- Writes take prescient's lock (.prescient-status.json.lock) and replace
  the file whole, re-reading under the lock, like write_status() does.
- Only repos that already gitignore prescient-status.json are written to,
  so no repo gains a stray tracked file.

Usage: no arguments runs in the foreground; --daemon detaches (see
herdr-plugin.toml); --once runs one tick; --explain prints, per agent, why
its icon looks the way it does.

Env: LIFEVIEW_AUTO_READY [1] (0 disables auto-ready), LIFEVIEW_SETTLE_S [60],
LIFEVIEW_STALE_OVERRIDE_S [300],
LIFEVIEW_AUTO_READY_STARTED [0] (1: also tasks the agent started itself),
BRO_URL [http://127.0.0.1:8766], PRESCIENT_URL [http://127.0.0.1:8765].
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

POLL_SECONDS = 10
SERVER_DEATH_TICKS = 10      # consecutive failed ticks before a daemon exits (as in claude-name)
AGENT_FRESH_S = 180          # an agent's own entry younger than this is never touched
HARNESS_WORKING_TTL = 300    # s: covers herdr's blind spot; refreshed while herdr still says working
STATUS_FILE = "prescient-status.json"
BY = "harness"
OURS = ("harness", "fallback")   # "fallback": this plugin's first version
SETTLE_S = float(os.environ.get("LIFEVIEW_SETTLE_S", "60"))
# An agent's own idle/standby older than this loses to herdr working/blocked
# when its transcript agrees (see stale_override()).
STALE_OVERRIDE_S = float(os.environ.get("LIFEVIEW_STALE_OVERRIDE_S", "300"))
TAIL_RECENT_S = 900          # a transcript entry older than this proves nothing (omp-watch's WORKING_STALE_SECONDS)
AUTO_READY = os.environ.get("LIFEVIEW_AUTO_READY", "1") != "0"
# A task the agent itself `bro task start`-ed: it knows the protocol, so its
# silence on `ready` is likely deliberate (e.g. idle while a background bench
# runs - seen live). Off by default; 1 lets auto-ready mark those too.
AUTO_READY_STARTED = os.environ.get("LIFEVIEW_AUTO_READY_STARTED", "0") == "1"
BRO_URL = os.environ.get("BRO_URL", "http://127.0.0.1:8766")
PRESCIENT_URL = os.environ.get("PRESCIENT_URL", "http://127.0.0.1:8765")
# Task hub cut-over switch (docs/go-task-hub.md wave 3): "bro" keeps today's
# behaviour; "prescient" routes create/list/ready through the hub service.
# Default bro so an older service is never required.
PLUGIN_CONFIG = Path.home() / ".config" / "herdr" / "plugins" / "config" / "dotfiles.lifeview-fallback" / "lifeview.env"


def _plugin_env(key: str, default: str = "") -> str:
    """An env value, else KEY= from the plugin's local config file (outside this
    repo). herdr launches this daemon without our env, so the config file is the
    only way to flip a switch for the live process."""
    v = os.environ.get("LIFEVIEW_" + key)
    if v:
        return v.strip().lower()
    try:
        for ln in PLUGIN_CONFIG.read_text().splitlines():
            k, _, val = ln.partition("=")
            if k.strip() == "LIFEVIEW_" + key and val.strip():
                return val.strip().lower()
    except OSError:
        pass
    return default


TASK_HUB = _plugin_env("TASK_HUB", "bro")
HUB_URL = PRESCIENT_URL
OPEN_TASK = ("open", "sent", "working")
# Auto-task: the harness opens a bro task for real work no task covers.
AUTO_TASK = os.environ.get("LIFEVIEW_AUTO_TASK", "1") != "0"
WORK_MIN_TOOL_CALLS = int(os.environ.get("LIFEVIEW_WORK_MIN_TOOL_CALLS", "2"))
WORK_MIN_SPAN_S = 90         # ... or one tool call and a turn running this long
JUST_DONE_S = 120            # a turn that ended this recently still gets its task (short sessions end between ticks)
# A task in any of these states already covers the agent's work: open/sent/
# working (handed or taken), reopened (the owner's "not quite" rework),
# noted (bro's list), ready (awaiting the owner's verdict - follow-up work
# belongs to it).
COVERING = ("open", "sent", "working", "reopened", "noted", "ready")
HARNESS_BY = "lifeview-harness"
BUSY = ("working", "blocked")

# herdr agent_status -> (state, line) for the harness entry
# While an agent settles toward auto-ready (see pending()), its entry stays
# `working`: without it the ring falls to its task's `queued`, which the
# dashboard draws grey, for the whole settle window (the grey flash).
SETTLING = ("working", "harness: settling, auto-ready pending")

FROM_HERDR = {
    "working": ("working", "harness: herdr reports working"),
    "idle": ("idle", "harness: herdr idle"),
    "done": ("idle", "harness: herdr idle"),
    "blocked": ("blocked", "harness: herdr blocked (approval dialog?)"),
}

# The dashboard's ring: lowest rank wins (index.html AG_RANK, BRO_STATES)
AG_RANK = {"ready": 0, "failed": 1, "blocked": 2, "working": 3, "queued": 4, "noted": 5,
           "done": 6, "dropped": 7, "idle": 8}
BRO_STATES = {"open": "queued", "sent": "queued", "reopened": "queued", "noted": "noted", "working": "working",
              "ready": "ready", "done": "done", "dropped": "dropped", "failed": "failed"}

HERDR_BIN = os.environ.get("HERDR_BIN_PATH", "herdr")
LOCK_PATH = Path("/tmp/lifeview-fallback.lock")
LOG_PATH = "/tmp/lifeview-fallback.log"
CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
_lock_handle: Optional[object] = None   # module-level so the flock outlives acquire()


def log(msg: str) -> None:
    print(f"[lifeview-fallback] {time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)


def acquire_singleton_lock() -> None:
    global _lock_handle
    _lock_handle = open(LOCK_PATH, "a")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
    _lock_handle.truncate(0)
    _lock_handle.write(str(os.getpid()))
    _lock_handle.flush()


# ---- pure decision logic: status file (unit-tested) ----

def epoch(iso: object) -> Optional[float]:
    try:
        at = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if at.tzinfo is None:
        at = at.astimezone()      # naive: local time
    return at.timestamp()


def age_s(entry: Dict, now: float) -> Optional[float]:
    at = epoch(entry.get("at"))
    return None if at is None else now - at


def is_ours(entry: object) -> bool:
    return isinstance(entry, dict) and entry.get("by") in OURS


def agent_fresh(entry: Dict, now: float) -> bool:
    age = age_s(entry, now)
    if age is None:
        return False
    if entry.get("ttl_s"):
        try:
            if age <= float(entry["ttl_s"]):
                return True
        except (TypeError, ValueError):
            pass
    return age < AGENT_FRESH_S


def compatible(state: str, herdr: str) -> bool:
    """Does a stale agent entry still stand against herdr's word? Only a
    `working` herdr no longer corroborates falls (prescient stops believing
    it past its 120 s grace anyway). idle/standby/blocked always stand:
    prescient believes them until replaced, and herdr's own "working" is
    known to stick for hours on omp panes, so it must not overrule an
    agent's settled word."""
    if state == "working":
        return herdr in ("working", "unknown")
    return True


def stale_override(e: Dict, herdr: str, tail: Optional[Dict], now: float) -> bool:
    """Does an agent's own entry lose to the harness? Only when all hold:
    1. it is idle/standby (never blocked: a human is being asked something)
       and older than STALE_OVERRIDE_S (the caller has already ruled out a
       fresh entry or one within its ttl_s);
    2. herdr says working or blocked;
    3. the transcript agrees: its newest recognizable entry is mid-turn
       (working, or an error for blocked) and younger than TAIL_RECENT_S.
       herdr alone is never enough (its omp "working" can stick for hours)."""
    if e.get("state") not in ("idle", "standby"):
        return False
    age = age_s(e, now)
    if age is None or age <= STALE_OVERRIDE_S:
        return False
    if herdr not in ("working", "blocked"):
        return False
    if not tail or tail.get("at") is None or now - tail["at"] > TAIL_RECENT_S:
        return False
    return tail.get("verdict") == "working" or (herdr == "blocked" and tail.get("verdict") == "error")


def decide(agent: Dict, entries: Dict, now: float, hold: bool = False,
           tail_of=None) -> Tuple[str, Optional[Dict]]:
    """What to do with one agent's entries: ("keep", None), ("write", entry)
    under its pane id, ("write_name", entry) under its herdr name, or
    ("drop", None) to remove our pane-id entry. hold: the agent is settling
    toward auto-ready, so it stays `working`. tail_of(agent): its transcript
    tail, asked only when a stale agent entry might be overridden."""
    pane, name = agent.get("pane_id") or "", agent.get("name") or ""
    herdr = agent.get("agent_status") or "unknown"
    by_name = entries.get(name) if name and name != pane else None
    by_pane = entries.get(pane)

    memo: list = []

    def get_tail() -> Optional[Dict]:   # read only when a line or an override needs it
        if not memo:
            memo.append(tail_of(agent) if tail_of else None)
        return memo[0]

    def overridden(e: Dict) -> Optional[Dict]:
        if agent_fresh(e, now) or e.get("state") not in ("idle", "standby") or herdr not in ("working", "blocked") \
                or not stale_override(e, herdr, get_tail(), now):
            return None
        state = FROM_HERDR[herdr][0]
        age = age_s(e, now) or 0
        suffix = f" (agent's {age / 60:.0f}m-old {e['state']} overridden)"
        entry = {"state": state, "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                 "line": activity_line(state, get_tail(), now)[: 200 - len(suffix)] + suffix, "by": BY,
                 "overrode": {"state": e["state"], "age_s": round(age), "line": str(e.get("line") or "")[:200]}}
        if state == "working":
            entry["ttl_s"] = float(HARNESS_WORKING_TTL)
        return entry

    # The agent's own word under its name: prescient reads that first, so a
    # pane-id entry of ours is a second source of truth. Leave the name entry
    # alone - unless it is stale and contradicted, then ours replaces it there.
    if isinstance(by_name, dict) and not is_ours(by_name):
        e = overridden(by_name)
        if e:
            return ("write_name", e)
        return ("drop", None) if is_ours(by_pane) else ("keep", None)

    if isinstance(by_pane, dict) and not is_ours(by_pane) and by_pane.get("state"):
        e = overridden(by_pane)
        if e:
            return ("write", e)
        if agent_fresh(by_pane, now) or compatible(str(by_pane.get("state")), herdr):
            return ("keep", None)

    if hold and herdr in ("idle", "done"):
        state, line = SETTLING
        if tail_of:
            line = activity_line("settling", get_tail(), now)
        ttl = SETTLE_S + 3 * POLL_SECONDS       # outlives the settle window, not a dead plugin by much
    elif herdr in FROM_HERDR:
        state, line = FROM_HERDR[herdr]
        if tail_of and state in ("working", "blocked"):
            line = activity_line(state, get_tail(), now)
        ttl = float(HARNESS_WORKING_TTL)
    else:
        return ("keep", None)          # unknown/absent: herdr has nothing to say
    carried = by_pane.get("overrode") if is_ours(by_pane) and by_pane.get("state") == state else None
    if carried:                        # still the override it was: keep saying what it replaced
        suffix = str(by_pane.get("line") or "")
        suffix = suffix[suffix.find(" (agent's "):] if " (agent's " in suffix else ""
        line = line[: 200 - len(suffix)] + suffix
    if is_ours(by_pane) and by_pane.get("by") == BY and (by_pane.get("state"), by_pane.get("line")) == (state, line):
        age = age_s(by_pane, now)
        if state != "working" or (age is not None and age < ttl / 2):
            return ("keep", None)
    entry = {"state": state, "at": datetime.now().astimezone().isoformat(timespec="seconds"), "line": line, "by": BY}
    if carried:
        entry["overrode"] = carried
    if state == "working":
        entry["ttl_s"] = float(ttl)
    return ("write", entry)


def plan(agents: list, entries: Dict, live_panes: set, now: float, holds: frozenset = frozenset(),
         tail_of=None) -> Dict[str, Optional[Dict]]:
    """Key -> new entry (None: delete) for one status file."""
    changes: Dict[str, Optional[Dict]] = {}
    for a in agents:
        action, entry = decide(a, entries, now, a["pane_id"] in holds, tail_of)
        if action == "write_name":
            changes[a["name"]] = entry
        elif action == "write":
            changes[a["pane_id"]] = entry
        elif action == "drop":
            changes[a["pane_id"]] = None
    for key, e in entries.items():      # ours, for panes herdr no longer lists
        if is_ours(e) and key not in live_panes and key not in changes:
            changes[key] = None
    return changes


# ---- transcripts ----

ACTIVITY_LOOKBACK = 60        # recognizable entries scanned back for what the agent is doing


def scan_tail(path: Path, max_bytes: int = 4 * 1024 * 1024) -> Dict:
    """The newest conversational entry of a claude or omp transcript, read
    backwards from EOF (complete lines only, as omp-watch does):
    {verdict, at, text, activity}. verdict is "answered" (an assistant
    message with text and no tool call: the turn's last word), "error" (an
    API/provider failure), or "working" (anything mid-turn: a user/tool-
    result entry, a tool call, thinking only). text is that answer's text,
    when answered. activity is what the current turn is doing, for the hover:
    its newest assistant text, else `running <tool>` for its newest tool call
    (the scan stops at the turn's user prompt, so an older turn never shows)."""
    out: Dict = {"verdict": None, "at": None, "text": "", "activity": None}
    tool = None
    seen = 0
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            pos, carry, scanned, first = size, b"", 0, True
            f.seek(max(size - 1, 0))
            terminated = size > 0 and f.read(1) == b"\n"
            while pos > 0 and scanned < max_bytes:
                n = min(65536, pos)
                pos -= n
                f.seek(pos)
                parts = (f.read(n) + carry).split(b"\n")
                scanned += n
                carry, lines = parts[0], parts[1:]
                if first:
                    first = False
                    if not terminated and lines:
                        lines = lines[:-1]
                for ln in reversed(lines):
                    v = classify(ln)
                    if not v:
                        continue
                    if seen == 0:
                        out.update(verdict=v["verdict"], at=v["at"], text=v["text"])
                    seen += 1
                    if v.get("said"):
                        out["activity"] = v["said"]
                        return out
                    tool = tool or v.get("tool")
                    if v.get("prompt") or seen >= ACTIVITY_LOOKBACK:
                        out["activity"] = f"running {tool}" if tool else None
                        return out
    except OSError:
        pass
    if tool:
        out["activity"] = f"running {tool}"
    return out


def classify(line: bytes) -> Optional[Dict]:
    """One entry's turn signal (see scan_tail), plus what it shows: said
    (assistant text, also beside a tool call), tool (the tool it calls),
    prompt (a user's prompt, which starts a turn - not a tool result)."""
    try:
        e = json.loads(line)
    except ValueError:
        return None
    if not isinstance(e, dict):
        return None
    msg = e.get("message") if isinstance(e.get("message"), dict) else {}
    role = msg.get("role")
    if role not in ("user", "assistant", "toolResult"):
        return None                     # bookkeeping entries carry no turn signal
    at = epoch(e.get("timestamp"))
    content = msg.get("content")
    blocks = content if isinstance(content, list) else [{"type": "text", "text": str(content or "")}]
    blocks = [b for b in blocks if isinstance(b, dict)]
    if role != "assistant":
        prompt = role == "user" and not e.get("isMeta") and not any(b.get("type") == "tool_result" for b in blocks)
        ptext = " ".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text").strip() if prompt else ""
        return {"verdict": "working", "at": at, "text": "", "prompt": prompt, "prompt_text": ptext}
    if e.get("isApiErrorMessage") or msg.get("stopReason") == "error":
        return {"verdict": "error", "at": at, "text": ""}
    text = " ".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text").strip()
    calls = [b for b in blocks if b.get("type") in ("tool_use", "toolCall")]
    tools = [b.get("name") for b in calls if b.get("name")]
    if calls:
        return {"verdict": "working", "at": at, "text": "", "said": text, "tool": tools[-1] if tools else None,
                "calls": len(calls)}
    if not text:
        return {"verdict": "working", "at": at, "text": ""}
    return {"verdict": "answered", "at": at, "text": text, "said": text}


def snippet(text: str, limit: int = 90) -> str:
    one = " ".join(str(text).split())
    return one if len(one) <= limit else one[: limit - 1].rstrip() + "…"


def activity_line(state: str, tail: Optional[Dict], now: float) -> str:
    """The hover line for a harness entry: what the transcript says the agent
    is doing, not a constant. <=200 chars, one line."""
    recent = bool(tail and tail.get("at") is not None and now - tail["at"] <= TAIL_RECENT_S)
    act = snippet(tail["activity"]) if recent and tail.get("activity") else None
    if state == "settling":
        line = f"settling · {act}" if act else "settling · auto-ready pending"
    elif state == "blocked":
        line = "blocked · waiting on an approval prompt" + (f" ({act})" if act else "")
    elif act:
        line = f"working · {act}"
    else:
        line = "working · starting (prompt received)" if recent else "working (no recent transcript activity)"
    return line[:200]


def scan_turn(path: Path, max_bytes: int = 8 * 1024 * 1024, max_entries: int = 3000) -> Dict:
    """The current turn of a transcript, back to its prompt: {key, start,
    prompt, calls, said, tool}. key is the prompt's own timestamp (one turn =
    one work session); None when the prompt is out of reach, and then no
    task is opened (a session that can't be identified can't be deduped)."""
    out: Dict = {"key": None, "start": None, "end": None, "prompt": "", "calls": 0, "said": "", "tool": None}
    seen = 0
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            pos, carry, scanned, first = size, b"", 0, True
            f.seek(max(size - 1, 0))
            terminated = size > 0 and f.read(1) == b"\n"
            while pos > 0 and scanned < max_bytes and seen < max_entries:
                n = min(65536, pos)
                pos -= n
                f.seek(pos)
                parts = (f.read(n) + carry).split(b"\n")
                scanned += n
                carry, lines = parts[0], parts[1:]
                if first:
                    first = False
                    if not terminated and lines:
                        lines = lines[:-1]
                for ln in reversed(lines):
                    v = classify(ln)
                    if not v:
                        continue
                    seen += 1
                    if out["end"] is None:
                        out["end"] = v.get("at")
                    if v.get("prompt"):
                        if v.get("at") is not None:
                            out.update(key=datetime.fromtimestamp(v["at"]).astimezone().isoformat(timespec="milliseconds"),
                                       start=v["at"], prompt=v.get("prompt_text") or "")
                        return out
                    out["calls"] += v.get("calls", 0)
                    out["said"] = out["said"] or v.get("said") or ""
                    out["tool"] = out["tool"] or v.get("tool")
    except OSError:
        pass
    return out


def session_marker(agent: Dict, turn: Dict) -> str:
    return f"[lifeview-session {agent.get('pane_id')}@{turn.get('key')}]"


def autotask_check(agent: Dict, tasks: list, turn: Dict, shown: Optional[set], now: float,
                   created: set = frozenset()) -> Tuple[Optional[str], str]:
    """(title for a new task, why) - or (None, why not). Opens a task only for
    a real work session no task covers, once per session."""
    if not AUTO_TASK:
        return None, "auto-task off (LIFEVIEW_AUTO_TASK=0)"
    herdr = agent.get("agent_status") or "unknown"
    if herdr in ("idle", "done"):
        end = turn.get("end")
        if end is None or now - end > JUST_DONE_S:
            return None, "not working, and no turn ended in the last 2 min"
    elif herdr != "working":
        return None, f"herdr says {herdr}"
    if shown is None or (agent.get("name") or agent.get("pane_id")) not in shown:
        return None, "not on the life view (prescient down, or a project it doesn't show)"
    covering = [t for t in tasks_of(agent, tasks) if t.get("state") in COVERING]
    if covering:
        return None, "covered by " + ", ".join(f"{t['id']} ({t['state']})" for t in covering)
    if not turn.get("key"):
        return None, "the turn's prompt is out of reach: session can't be identified"
    marker = session_marker(agent, turn)
    if marker in created or any(marker in str(h.get("note") or "") for t in tasks for h in t.get("history") or []):
        return None, "a task was already opened for this session"
    calls = turn.get("calls", 0)
    span = (turn.get("end") if herdr in ("idle", "done") and turn.get("end") else now) - (turn.get("start") or now)
    if not (calls >= WORK_MIN_TOOL_CALLS or (calls >= 1 and span > WORK_MIN_SPAN_S)):
        return None, f"trivial so far: {calls} tool call(s), {span:.0f}s (needs {WORK_MIN_TOOL_CALLS}, or 1 and >{WORK_MIN_SPAN_S}s)"
    what = turn.get("said") or turn.get("prompt") or (f"running {turn['tool']}" if turn.get("tool") else "work")
    return "auto: " + snippet(what, 114), f"work session: {calls} tool calls, {span:.0f}s, no task covering it"


def _omp_newest_session():
    """omp-watch's proven cwd -> newest omp session file lookup."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "omp-watch"))
        import watch  # type: ignore
        return watch.newest_session_file
    except Exception:
        return None
    finally:
        sys.path.pop(0)


_omp_session = _omp_newest_session()


def interactive(path: Path) -> bool:
    """A claude transcript from an interactive session (entrypoint "cli"), not
    a headless `claude -p` / SDK run (entrypoint "sdk-cli")."""
    try:
        with path.open("rb") as f:
            f.seek(max(path.stat().st_size - 65536, 0))
            return b'"entrypoint":"cli"' in f.read()
    except OSError:
        return False


def transcript_of(agent: Dict, agents: list) -> Optional[Path]:
    """herdr's session id goes stale (seen live: a pane on a session 14 h
    newer than its claim), so for the only claude pane in a cwd the newest
    interactive transcript in that cwd's project folder wins."""
    if agent.get("agent") == "claude":
        sess = (agent.get("agent_session") or {}).get("value")
        claimed = next(iter(CLAUDE_PROJECTS.glob(f"*/{sess}.jsonl")), None) if sess else None
        cwd = agent.get("cwd") or ""
        if sum(1 for a in agents if a.get("agent") == "claude" and a.get("cwd") == cwd) == 1:
            folder = CLAUDE_PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", cwd)
            try:
                files = sorted(folder.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
            except OSError:
                files = []
            newest = next((f for f in files[:8] if interactive(f)), None)
            if newest and (claimed is None or newest.stat().st_mtime > claimed.stat().st_mtime):
                return newest
        return claimed
    if agent.get("agent") == "omp" and _omp_session:
        cwd = agent.get("cwd") or ""
        # newest file per cwd: only unambiguous with one omp in that cwd
        if sum(1 for a in agents if a.get("agent") == "omp" and a.get("cwd") == cwd) == 1:
            return _omp_session(cwd)
    return None


# ---- auto-ready (unit-tested) ----

def summary_of(text: str, limit: int = 240) -> str:
    one = " ".join(text.split())
    return "auto: " + (one if len(one) <= limit else one[: limit - 1].rstrip() + "…")


def tasks_for(agent: Dict, tasks: list) -> list:
    """Open bro tasks whose agent is this one (by herdr name or pane id)."""
    return [t for t in tasks_of(agent, tasks) if t.get("state") in OPEN_TASK]


def tasks_of(agent: Dict, tasks: list) -> list:
    """Every bro task whose agent is this one: its `agent`, else an agent:<name> dest
    (how bro and the dashboard attribute it)."""
    keys = {agent.get("name"), agent.get("pane_id")} - {None, ""}
    def who(t: Dict) -> Optional[str]:
        dest = str(t.get("dest") or "")
        return t.get("agent") or (dest.split(":", 1)[1] if dest.startswith("agent:") else None)
    return [t for t in tasks if who(t) in keys]


SESSION_RE = re.compile(r"\[lifeview-session [^@\]]+@([^\]]+)\]")


def task_at(t: Dict) -> Optional[float]:
    """When the task was last handed over or moved. For a task the harness
    opened (and nobody moved since), its work session's start: it may be
    opened after that session's answer, which must still count."""
    hist = t.get("history") or []
    last = hist[-1] if hist else {}
    m = SESSION_RE.search(str(last.get("note") or "")) if last.get("by") == HARNESS_BY else None
    if m and epoch(m.group(1)) is not None:
        return epoch(m.group(1))
    return epoch(last.get("at") or t.get("created"))


def ready_check(agent: Dict, tasks: list, project_busy: List[str], tail: Dict, now: float) -> Tuple[Optional[Dict], str]:
    """(task to mark ready, why) - or (None, why not). Every condition must
    hold; each guards a way auto-ready could show a false green."""
    if not AUTO_READY:
        return None, "auto-ready off (LIFEVIEW_AUTO_READY=0)"
    mine = tasks_for(agent, tasks)
    if not mine:
        return None, "no open bro task for it"
    if len(mine) > 1:
        return None, f"{len(mine)} open bro tasks: ambiguous, left to the agent"
    t = mine[0]
    keys = {agent.get("name"), agent.get("pane_id")}
    if not AUTO_READY_STARTED and any(h.get("state") == "working" and h.get("by") in keys for h in t.get("history") or []):
        return None, f"{t['id']} was started by the agent itself: `ready` is its call (LIFEVIEW_AUTO_READY_STARTED=1 overrides)"
    herdr = agent.get("agent_status") or "unknown"
    if herdr not in ("idle", "done"):
        return None, f"herdr says {herdr}, not settled"
    if project_busy:
        return None, "another agent in its project is busy: " + ", ".join(project_busy)
    if tail.get("verdict") != "answered":
        return None, f"transcript tail is {tail.get('verdict') or 'unreadable'}, not a finished answer"
    if tail.get("at") is None:
        return None, "transcript tail has no timestamp"
    quiet = now - tail["at"]
    if quiet < SETTLE_S:
        return None, f"settling: quiet {quiet:.0f}s of {SETTLE_S:.0f}s"
    handed = task_at(t)
    if handed is None or tail["at"] <= handed:
        return None, "no answer since the task was handed over / last moved"
    if tail.get("text", "").rstrip().endswith("?"):
        return None, "its last message asks a question: waiting on the owner, not ready"
    return t, f"settled {quiet:.0f}s after answering; one open task {t['id']}"


def pending(agent: Dict, tasks: list, project_busy: List[str], tail: Dict, now: float) -> bool:
    """Settling toward auto-ready: not ready now, but would be once the settle
    window has passed with nothing else changing. Every other guard still
    applies, so an agent that won't go green (a question, a task it started,
    no task) is never held."""
    if ready_check(agent, tasks, project_busy, tail, now)[0] is not None:
        return False
    return ready_check(agent, tasks, project_busy, tail, now + SETTLE_S)[0] is not None


# ---- herdr, bro, filesystem ----

def list_agents() -> list:
    proc = subprocess.run([HERDR_BIN, "agent", "list"], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "agent list failed")
    return json.loads(proc.stdout)["result"]["agents"]


def http_json(url: str, body: Optional[Dict] = None, timeout: float = 3) -> Optional[Dict]:
    """GET (or POST body) a JSON endpoint; None when the service is down."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read())
    except Exception:
        return None


def bro_tasks() -> Optional[list]:
    if TASK_HUB == "prescient" and hub_available():
        return bro_tasks_via_hub()
    got = http_json(BRO_URL + "/api/tasks")
    if not isinstance(got, dict):
        return None
    return [t for t in got.get("tasks") or [] if isinstance(t, dict) and t.get("id")]


def bro_bin() -> Optional[str]:
    """bro's CLI (task creation has no HTTP route): LIFEVIEW_BRO_BIN, else
    BRO_BIN= in the plugin's local config file (outside this repo), else PATH."""
    if os.environ.get("LIFEVIEW_BRO_BIN"):
        return os.environ["LIFEVIEW_BRO_BIN"]
    try:
        for ln in PLUGIN_CONFIG.read_text().splitlines():
            k, _, v = ln.partition("=")
            if k.strip() == "BRO_BIN" and v.strip():
                return os.path.expanduser(os.path.expandvars(v.strip()))
    except OSError:
        pass
    return shutil.which("bro")


def hub_available() -> bool:
    """True when the prescient task hub answers. Cached briefly: the plugin
    ticks every 10 s and must not add a probe per tick per agent."""
    global _HUB_OK
    now = time.time()
    if _HUB_OK and now - _HUB_OK[0] < 30:
        return _HUB_OK[1]
    got = http_json(HUB_URL + "/api/tasks?state=queued&limit=1", timeout=2)
    ok = isinstance(got, dict) and isinstance(got.get("items"), list)
    _HUB_OK = (now, ok)
    return ok


_HUB_OK: tuple = (0.0, False)


def hub_open_task(agent: Dict, title: str, turn: Dict) -> Optional[str]:
    """Harness create through the hub (wave 3): project is REQUIRED and comes
    from the git toplevel, never derived from a dest string."""
    project = project_name(agent)
    if not project:
        return None
    who = agent.get("name") or agent["pane_id"]
    note = (f"opened by the lifeview harness: {who} began work with no task covering it "
            f"(LIFEVIEW_AUTO_TASK=0 disables this) {session_marker(agent, turn)}")
    got = http_json(HUB_URL + "/api/tasks", {"op": "create", "text": title, "project": project,
                                             "target": "coordinator", "origin": "harness", "note": note})
    item = (got or {}).get("item") or {}
    return item.get("id") if item.get("id") else None


def hub_mark_ready(t: Dict, agent: Dict, tail: Dict, quiet: float) -> Optional[Dict]:
    who = agent.get("name") or agent.get("pane_id")
    note = ("auto-marked ready by the lifeview harness: " + who +
            f" settled {quiet:.0f}s after its last answer with this as its one open task; "
            "summary is that answer. LIFEVIEW_AUTO_READY=0 disables this.")
    return http_json(HUB_URL + "/api/tasks", {"op": "ready", "id": t["id"], "by": who,
                                              "summary": summary_of(tail.get("text", "")), "note": note})


def bro_tasks_via_hub() -> Optional[list]:
    got = http_json(HUB_URL + "/api/tasks", timeout=3)
    if not isinstance(got, dict):
        return None
    return [i for i in got.get("items") or [] if isinstance(i, dict) and i.get("id")]


def open_task(agent: Dict, title: str, turn: Dict) -> Optional[str]:
    """`bro task add` for the agent, left `sent` (it may still `start` it).
    By the harness, so auto-ready's started-by-the-agent exclusion never
    applies. Returns the new task id, or None."""
    exe = bro_bin()
    if not exe:
        return None
    who = agent.get("name") or agent["pane_id"]
    note = (f"opened by the lifeview harness: {who} began work with no task covering it "
            f"(LIFEVIEW_AUTO_TASK=0 disables this) {session_marker(agent, turn)}")
    try:
        proc = subprocess.run([exe, "task", "add", title, "--dest", f"agent:{who}", "--to", who,
                               "--by", HARNESS_BY, "--note", note], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.match(r"(tk-[0-9a-f]+) is open", proc.stdout.strip())
    return m.group(1) if proc.returncode == 0 and m else None


def mark_ready(t: Dict, agent: Dict, tail: Dict, quiet: float) -> Optional[Dict]:
    if TASK_HUB == "prescient" and hub_available():
        return hub_mark_ready(t, agent, tail, quiet)
    who = agent.get("name") or agent.get("pane_id")
    note = (f"auto-marked ready by the lifeview harness: {who} settled {quiet:.0f}s after its last answer "
            "with this as its one open task; summary is that answer. LIFEVIEW_AUTO_READY=0 disables this.")
    return http_json(BRO_URL + "/api/tasks", {"action": "ready", "id": t["id"], "by": who,
                                              "summary": summary_of(tail.get("text", "")), "note": note})


def project_name(agent: Dict) -> Optional[str]:
    """The hub's REQUIRED project: the git toplevel's basename (the same rule
    `prescient status` and the CLI use), never derived from a dest string."""
    root = git_root(str(agent.get("cwd") or ""))
    if not root:
        return None
    # The board's rule (prescient's gantt.agent.project_of): the repo folder's
    # name with a leading dot dropped -- `.dotfiles` is "dotfiles". Matching it
    # is what keeps one project from splitting into two on the hub.
    return os.path.basename(root).lstrip(".") or None


def git_root(cwd: str) -> Optional[str]:
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return top.stdout.strip() if top.returncode == 0 else None


def writable(root: str) -> bool:
    """The repo already gitignores the status file and the lock created next to it."""
    try:
        ign = subprocess.run(["git", "-C", root, "check-ignore", STATUS_FILE, "." + STATUS_FILE + ".lock"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return len(ign.stdout.split()) == 2


def repo_root(cwd: str) -> Optional[str]:
    """The git toplevel of cwd, as `prescient status` resolves it, if it is writable()."""
    root = git_root(cwd)
    return root if root and writable(root) else None


def read_entries(path: Path) -> Tuple[Dict, Dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    agents = raw.get("agents") if isinstance(raw.get("agents"), dict) else {}
    return raw, agents


def apply(root: str, agents: list, live_panes: set, holds: frozenset = frozenset(), tail_of=None) -> None:
    """Re-read and decide under prescient's lock, so an agent's write between
    our look and our write is never clobbered."""
    path = Path(root) / STATUS_FILE
    _, peek = read_entries(path)
    if not plan(agents, peek, live_panes, time.time(), holds, tail_of):
        return                          # nothing to do: don't touch the lock
    with open(path.with_name("." + STATUS_FILE + ".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        raw, entries = read_entries(path)
        changes = plan(agents, entries, live_panes, time.time(), holds, tail_of)
        if not changes:
            return
        for key, entry in changes.items():
            before = entries.get(key)
            if entry is None:
                entries.pop(key, None)
                log(f"{root}: {key} harness entry removed")
            elif entry.get("overrode") and not (is_ours(before) and before.get("overrode")):
                entries[key] = entry
                o = entry["overrode"]
                log(f"{root}: {key} -> {entry['state']} (overrode stale agent {o['state']}, {o['age_s']}s)")
            else:
                entries[key] = entry
                if not (is_ours(before) and before.get("state") == entry["state"]):   # line-only refreshes stay quiet
                    # never the transcript-derived part: it can be private project content
                    log(f"{root}: {key} -> {entry['state']} ({entry['line'] if entry['line'].startswith('harness:') else 'harness, from the transcript'})")
        tmp = path.with_name("." + STATUS_FILE + ".tmp")
        tmp.write_text(json.dumps({**raw, "agents": entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)


class World:
    """One look at herdr: agents, their repos, and who in each project is busy."""

    def __init__(self) -> None:
        self.agents = [a for a in list_agents() if a.get("pane_id")]
        self.live = {a["pane_id"] for a in self.agents}
        roots: Dict[str, Optional[str]] = {}
        self.root: Dict[str, Optional[str]] = {}
        for a in self.agents:
            cwd = a.get("cwd") or ""
            if cwd not in roots:
                roots[cwd] = git_root(cwd)
            self.root[a["pane_id"]] = roots[cwd]

    def project_busy(self, agent: Dict) -> List[str]:
        mine = self.root.get(agent["pane_id"])
        return [f"{a.get('name') or a['pane_id']} ({a.get('agent_status')})" for a in self.agents
                if a is not agent and mine and self.root.get(a["pane_id"]) == mine and a.get("agent_status") in BUSY]


class Harness:
    def __init__(self) -> None:
        self.failed: Dict[str, str] = {}      # root -> last error, so a stuck repo logs once
        self.last_why: Dict[str, str] = {}    # pane -> last auto-ready verdict worth logging
        self.seen_roots: set = set()          # repos written to: still swept once their agents are gone
        self.created: set = set()             # session markers opened this run (bro's list is the durable record)

    def tick(self) -> None:
        w = World()
        tasks = bro_tasks() if (AUTO_READY or AUTO_TASK) else None
        self.auto_task(w, tasks)
        tails = self.tails(w, tasks)
        # Mark ready BEFORE the status write: the hold is released only once
        # the task is green, so no board read can land between the two.
        self.auto_ready(w, tasks, tails)
        now = time.time()
        holds = frozenset(a["pane_id"] for a in w.agents if a["pane_id"] in tails
                          and pending(a, tasks or [], w.project_busy(a), tails[a["pane_id"]], now))

        def tail_of(a: Dict) -> Dict:          # read on demand: only override candidates ask
            if a["pane_id"] not in tails:
                path = transcript_of(a, w.agents)
                tails[a["pane_id"]] = scan_tail(path) if path else {"verdict": None, "at": None, "text": ""}
            return tails[a["pane_id"]]
        by_root: Dict[str, list] = {}
        writable_roots: Dict[str, bool] = {}
        for a in w.agents:
            root = w.root.get(a["pane_id"])
            if root is None:
                continue
            if root not in writable_roots:
                writable_roots[root] = writable(root)
            if writable_roots[root]:
                by_root.setdefault(root, []).append(a)
        self.seen_roots |= set(by_root)
        for root in self.seen_roots - set(by_root):
            by_root[root] = []                # no live agent left: only removes our dead-pane entries
        for root, group in by_root.items():
            try:
                apply(root, group, w.live, holds, tail_of)
                self.failed.pop(root, None)
            except Exception as exc:       # one repo must not stop the rest
                if self.failed.get(root) != str(exc):
                    self.failed[root] = str(exc)
                    log(f"{root}: {exc}")

    def auto_task(self, w: World, tasks: Optional[list]) -> None:
        """Open a task for each agent starting real work no task covers; it
        joins `tasks` at once, so this tick's auto-ready and hold see it."""
        if not AUTO_TASK or tasks is None:
            return
        board = http_json(PRESCIENT_URL + "/api/agent-board")
        shown = {r.get("name") for r in (board or {}).get("agents") or []} if board else None
        now = time.time()
        for a in w.agents:
            herdr = a.get("agent_status")
            if herdr not in ("working", "idle", "done") or any(t.get("state") in COVERING for t in tasks_of(a, tasks)):
                continue                      # cheap checks first: no transcript read
            path = transcript_of(a, w.agents)
            if not path:
                continue
            if herdr != "working":            # only a turn that just ended: a cheap tail look first
                last = scan_tail(path).get("at")
                if last is None or now - last > JUST_DONE_S:
                    continue
            turn = scan_turn(path)
            title, why = autotask_check(a, tasks, turn, shown, now, self.created)
            if not title:
                continue
            marker = session_marker(a, turn)
            self.created.add(marker)          # once per session, even if bro's list lags or the add fails
            tid = open_task(a, title, turn)
            who = a.get("name") or a["pane_id"]
            if tid:
                log(f"bro {tid} opened (auto) for {who}: {why}")
                tasks.append({"id": tid, "state": "sent", "agent": who, "dest": f"agent:{who}",
                              "history": [{"at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                           "state": "sent", "by": HARNESS_BY, "note": marker}]})
            else:
                log(f"auto-task for {who} failed (bro CLI: {bro_bin() or 'not found'})")

    @staticmethod
    def tails(w: World, tasks: Optional[list]) -> Dict[str, Dict]:
        """Transcript tails, read only for agents with an open bro task."""
        out: Dict[str, Dict] = {}
        for a in w.agents:
            if tasks and tasks_for(a, tasks):
                path = transcript_of(a, w.agents)
                out[a["pane_id"]] = scan_tail(path) if path else {"verdict": None, "at": None, "text": ""}
        return out

    def auto_ready(self, w: World, tasks: Optional[list], tails: Dict[str, Dict]) -> None:
        if not AUTO_READY or tasks is None:
            return                        # off, or bro down: nothing to mark
        now = time.time()
        for a in w.agents:
            tail = tails.get(a["pane_id"])
            if tail is None:
                continue
            t, why = ready_check(a, tasks, w.project_busy(a), tail, now)
            if t is None:
                continue
            got = mark_ready(t, a, tail, now - tail["at"])
            who = a.get("name") or a["pane_id"]
            if got and (got.get("task") or {}).get("state") == "ready":
                log(f"bro {t['id']} -> ready (auto) for {who}: {why}")
                t["state"] = "ready"          # this tick's copy: not again
            elif self.last_why.get(a["pane_id"]) != "mark failed":
                self.last_why[a["pane_id"]] = "mark failed"
                log(f"bro {t['id']}: auto-ready for {who} failed: {got}")


# ---- --explain ----

def icon_state(row_status: str, task_states: List[str]) -> str:
    """The ring for one agent alone, as agentGroups() ranks it."""
    cands = [BRO_STATES.get(s, "queued") for s in task_states]
    if row_status in ("blocked", "working"):
        cands.append(row_status)
    return min(cands, key=lambda s: AG_RANK.get(s, 99)) if cands else "idle"


def explain() -> None:
    w = World()
    tasks = bro_tasks()
    board = http_json(PRESCIENT_URL + "/api/agent-board") or {}
    rows = {r.get("name"): r for r in board.get("agents") or []}
    now = time.time()
    print(f"bro: {'up' if tasks is not None else 'DOWN (no tasks, no auto-ready)'}; "
          f"prescient: {'up' if board else 'DOWN (icon state computed locally)'}; auto-ready {'on' if AUTO_READY else 'off'}")
    for a in w.agents:
        name = a.get("name") or a["pane_id"]
        herdr = a.get("agent_status") or "unknown"
        path = transcript_of(a, w.agents)
        tail = scan_tail(path) if path else {"verdict": None, "at": None, "text": ""}
        root = w.root.get(a["pane_id"])
        entries = read_entries(Path(root) / STATUS_FILE)[1] if root else {}
        e = entries.get(a.get("name") or "") or entries.get(a["pane_id"])
        mine = tasks_of(a, tasks or [])
        row = rows.get(name) or {}
        status = row.get("status") or (e.get("state") if isinstance(e, dict) else None) or herdr
        relevant = [t["state"] for t in mine if t.get("state") not in ("done", "dropped")]
        icon = icon_state(status, relevant)
        print(f"\n{name} [{a['pane_id']}, {a.get('agent')}] -> icon: {icon}")
        print(f"  herdr: {herdr}")
        if path:
            age = f"{now - tail['at']:.0f}s ago" if tail.get("at") else "no timestamp"
            print(f"  transcript: {tail.get('verdict') or 'unreadable'}, {age}  ({path.name})")
        else:
            print("  transcript: not found" + (" (several omp in one cwd)" if a.get("agent") == "omp" else ""))
        if isinstance(e, dict):
            who = "harness" if is_ours(e) else "the agent"
            print(f"  prescient-status.json: {e.get('state')} by {who}, {age_s(e, now) or 0:.0f}s old: {e.get('line', '')}")
        else:
            print("  prescient-status.json: no entry" + ("" if root and writable(root) else " (repo doesn't gitignore it: not written)"))
        if row:
            print(f"  dashboard row: status {row.get('status')}" + (f" (herdr {row['herdr']})" if row.get("herdr") else ""))
        print("  bro tasks: " + (", ".join(f"{t['id']} {t['state']}" for t in mine if t.get("state") not in ("done", "dropped")) or "none open"))
        if tasks is not None:
            print("  auto-ready: " + ready_check(a, tasks, w.project_busy(a), tail, now)[1])
            turn = scan_turn(path) if path else {}
            shown = set(rows) if board else None
            print("  auto-task: " + autotask_check(a, tasks, turn, shown, now)[1])
        open_tasks = [t for t in mine if t.get("state") not in ("done", "dropped")]
        print("  why: " + why_icon(icon, herdr, status, e, open_tasks))


def why_icon(icon: str, herdr: str, status: str, e: object, tasks: Optional[list] = None) -> str:
    from_task = next((t for t in tasks or [] if BRO_STATES.get(t.get("state"), "queued") == icon), None)
    if icon == "ready":
        return f"bro task {from_task['id'] if from_task else '?'} is ready for your verdict (green)"
    if from_task and icon != status:
        return f"{icon}, from bro task {from_task['id']} ({from_task['state']}); the agent's own status is {status}"
    if icon in ("working", "blocked"):
        src = "the agent's own entry" if isinstance(e, dict) and not is_ours(e) else "herdr (via the harness)"
        return f"{icon}, from {src}"
    if icon == "idle":
        if herdr == "unknown" and not isinstance(e, dict):
            return "dim: herdr can't tell its state and it hasn't reported itself"
        return f"dim: idle ({status}) with no open task needing you"
    return f"{icon}: from its bro task"


def run() -> None:
    h = Harness()
    tick_errors = 0
    while True:
        try:
            h.tick()
            tick_errors = 0
        except Exception as exc:
            tick_errors += 1
            if tick_errors == 1:
                log(f"tick failed: {exc}")
            if tick_errors >= SERVER_DEATH_TICKS:
                log("herdr unreachable for too long; exiting")
                return
        time.sleep(POLL_SECONDS)


def daemonize() -> None:
    if os.fork():
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)
    log_fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    for fd in (0, 1, 2):
        os.dup2(log_fd, fd)
    if log_fd > 2:
        os.close(log_fd)


if __name__ == "__main__":
    if "--explain" in sys.argv:
        explain()
        sys.exit(0)
    if "--once" in sys.argv:
        Harness().tick()
        sys.exit(0)
    if "--daemon" in sys.argv:
        daemonize()
    acquire_singleton_lock()
    run()
