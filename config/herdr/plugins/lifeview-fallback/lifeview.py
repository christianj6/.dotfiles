#!/usr/bin/env python3
"""Keep prescient's life-view icons true from the harness, without agents.

The life view shows each agent's state from two sources. This plugin feeds
both, so no agent has to remember a CLI:

1. The inner line comes from <repo>/prescient-status.json. Each tick, herdr's
   own agent_status is written there for every agent that hasn't spoken for
   itself. omp's herdr status is already transcript-backed (omp-watch), and
   claude's comes from its hooks.
2. The ring is green when a hub item is `ready`. Readiness is the PROJECT's:
   items match on project + target (the hub sets no agent/dest). When the
   project's omp settles after an answer, with one open item awaiting ready,
   the plugin marks it ready (by: harness), the summary being the last
   answer of whoever did the work - the project's claude when it did,
   else the omp ("auto: " summary prefix). See ready_check() for every
   condition and ready_candidate() for the state predicate;
   LIFEVIEW_AUTO_READY=0 turns it off.

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
from urllib.parse import quote
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

AUTO_READY = _plugin_env("AUTO_READY", "1") != "0"
# A task the agent itself `bro task start`-ed: it knows the protocol, so its
# silence on `ready` is likely deliberate (e.g. idle while a background bench
# runs - seen live). Off by default; 1 lets auto-ready mark those too.
AUTO_READY_STARTED = _plugin_env("AUTO_READY_STARTED", "0") == "1"
BRO_URL = os.environ.get("BRO_URL", "http://127.0.0.1:8766")
PRESCIENT_URL = os.environ.get("PRESCIENT_URL", "http://127.0.0.1:8765")
# Task hub cut-over switch (docs/go-task-hub.md wave 3): "bro" keeps today's
# behaviour; "prescient" routes create/list/ready through the hub service.
# Default bro so an older service is never required.
TASK_HUB = _plugin_env("TASK_HUB", "bro")
HUB_URL = PRESCIENT_URL
# The hub's own vocabulary (prescient/tasks/store.py STATES). Auto-ready reads
# these and nothing else: see hub_open() and ready_candidate().
HUB_STATES = ("created", "queued", "working", "ready", "parked", "undelivered", "done")
HUB_CLOSED = ("done",)            # a dropped item arrives as done + resolution=dropped
HUB_TARGETS = ("coordinator", "dev")
# How the harness brings a candidate to ready, per the hub's TRANSITIONS: ready
# is reachable only from working, and queued -> working is a plain start.
# created/parked/undelivered have no harness route (create queues at once;
# unpark and retry are someone else's call), so they are reported, not marked.
READY_ROUTE = {"working": ("ready",), "queued": ("start", "ready")}
# Auto-task: the harness opens a bro task for real work no task covers.
AUTO_TASK = _plugin_env("AUTO_TASK", "1") != "0"   # env or the plugin config file (the daemon has no env)
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
AG_RANK_VERSION = 2   # prescient's published rank table version
AG_RANK = {"ready": 0, "failed": 1, "blocked": 2, "working": 3, "queued": 4, "noted": 5,
           "done": 6, "dropped": 7, "idle": 8}
# DISPLAY ONLY: bro-local states -> the ring's vocabulary. Never a filter for auto-ready (that is hub_open/ready_candidate).
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
        blob = " ".join(
            " ".join(str(x) for x in (b.get("arguments"), b.get("intent")) if x)
            for b in calls
        )
        return {"verdict": "working", "at": at, "text": "", "said": text, "tool": tools[-1] if tools else None,
                "calls": len(calls), "tools": tools, "did": blob[:2000]}
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
    out: Dict = {"key": None, "start": None, "end": None, "prompt": "", "calls": 0, "said": "", "tool": None,
                 "tools": [], "did": ""}
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
                    for t in v.get("tools") or []:
                        if t not in out["tools"]:
                            out["tools"].append(t)
                    if v.get("did"):
                        out["did"] = (out["did"] + " " + v["did"])[:4000]
    except OSError:
        pass
    return out


def session_marker(agent: Dict, turn: Dict) -> str:
    return f"[lifeview-session {agent.get('pane_id')}@{turn.get('key')}]"


# Tools whose arguments name the task system. A turn that touches any of these
# is the coordinator WORKING ON the hub, not doing project work -- auto-tasking
# it would create a card about the card that was just created, which nudges the
# agent, whose next turn does it again (the self-referential loop, 2026-11-03).
TASK_SYSTEM_TOOLS = ("Bash", "bash", "shell", "exec", "terminal")
TASK_SYSTEM_ARG = re.compile(
    r"(\bprescient\s+task\b|\bbro\s+task\b|/api/tasks|tasks\.sqlite3|prescient-status\.json"
    r"|lifeview|taskhub|\bhub\.py\b)", re.I)


# ---- provenance: whose words started this turn (docs/design-task-provenance.md) ----

# Machinery is not work. These arrive through the same chat input as the owner's
# sentences but nobody asked for anything: the harness notifying about a
# background task, omp resuming a context-exhausted session, an image pasted on
# its own. They must never become a tracked card (22 of heinzel's 65 turns were
# these, all of them previously eligible).
MACHINERY_PROMPT = re.compile(
    r"^\s*(?:<task-notification>|<task-|<local-command|This session is being continued from a previous"
    r"|\[Image:[^\]]*\]\s*$|\[Request interrupted)", re.I)

# An agent handing work to its worker, rather than the owner asking: this project's
# own convention is a round spec ("Round 25: ...") or a spec path. Evidence in the
# text, never guessed.
AGENT_PROMPT = re.compile(r"^\s*(?:Round \d+|Spec:|Notes:|Discussion, no code)"
                          r"|^\s*\S*(?:docs|specs|release/docs)/\S+\.md\b", re.I)


# Known omp comms shapes. A coordinator's pane receives machinery, relays from
# other agents, and free-form worker reports -- all through the same input box, with
# no sender field in the transcript. Classifying them by SHAPE is the only signal
# available (every entry carries attribution:"user"), and opening the owner gate
# without it turned hub nudges into cards, which nudged the omp again: the
# self-referential loop of 2026-11-03 (docs/design-delivery-provenance.md).
#
# A real fix records the sender at delivery (prescient's _deliver knows it); until
# that lands these markers keep the gate honest. Free-form worker reports carry no
# marker and stay unattributable -- the safe reading.
OMP_MACHINERY = re.compile(
    r"^\s*(?:prescient: |prescient task |\[lifeview|bro request tr-|"
    r"\d+ tweaks? (?:sent|waiting)|a tweak was sent)", re.I)
OMP_AGENT = re.compile(
    r"^\s*(?:From claude-|From omp-|From [a-z0-9.-]+ \(prescient|Task from the |"
    r"REPORT\b|WAVE \d|Card \d)", re.I)
OWNER_MARKED = re.compile(r"^\s*From the owner", re.I)

# The sender's tag (docs/design-message-tags.md): one first line written by the
# sender, which KNOWS who it is -- `omp-peer send` puts it on every agent-to-agent
# message, e.g. "[from:coordinator project:bro id:omp-v35-wdp5]". It is the answer,
# not a guess, so it is read before every shape rule below.
TAG = re.compile(r"^\s*\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]")
TAG_ORIGIN = {
    "owner": "owner",           # beats every shape: the owner's words can look like anything
    "coordinator": "agent",
    "worker": "agent",
    "bro": "agent",
    "harness": "machinery",     # never a card: what keeps the 2026-11-03 loop shut
}


def untagged(prompt: str) -> str:
    """The prompt without its sender tag: the words that were asked, for a card."""
    m = TAG.match(prompt)
    return prompt[m.end():].strip() if m else prompt


def prompt_provenance(turn: Dict) -> Optional[str]:
    """'machinery' | 'agent' | 'owner': from the sender's tag when there is one,
    else from the prompt's SHAPE.

    Whole-classification of the turn's prompt, done once, at the place the card is
    created. Never re-derived downstream: a consumer guessing provenance from text
    is the same bug as the agent-keyed auto-ready. Returns None when there is no
    prompt to judge, and the caller then opens nothing (a turn that cannot be
    attributed must not be invented as the owner's).
    """
    prompt = str(turn.get("prompt") or "").strip()
    if not prompt:
        return None
    tag = TAG.match(prompt)
    if tag:
        return TAG_ORIGIN[tag.group(1)]     # the sender said who it is: no shape rule applies
    # Untagged: today's behaviour, unchanged -- machinery shapes, then the comms
    # shapes, then the owner (untagged is overwhelmingly the owner typing).
    if MACHINERY_PROMPT.match(prompt):
        return "machinery"
    if OWNER_MARKED.match(prompt):
        return "owner"                      # explicitly from the owner (bro's relay marks it)
    if OMP_MACHINERY.match(prompt):
        return "machinery"                  # hub nudges, tweak notices, life view: never work
    if OMP_AGENT.match(prompt) or AGENT_PROMPT.match(prompt):
        return "agent"                      # a relay from another agent, a round spec
    return "owner"


def task_system_turn(turn: Dict) -> bool:
    """True when this turn's own commands/prompt are about the task system."""
    blob = " ".join(str(x or "") for x in (
        turn.get("prompt"), turn.get("said"), turn.get("did"),
        " ".join(turn.get("tools") or []),
    ))
    if TASK_SYSTEM_ARG.search(blob):
        return True
    # a tool name alone is not enough (Bash is used for everything); the
    # argument scan above is what decides.
    return False


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
    if task_system_turn(turn):
        return None, "this turn is about the task system itself (hub/CLI/tray) - auto-task would loop on its own output"
    origin = prompt_provenance(turn)
    if origin is None:
        return None, "no prompt to attribute: nothing is opened for work nobody can be shown to have asked for"
    if origin == "machinery":
        return None, "not work: a harness notification, a resumed session or a pasted image (never a card)"
    # A coordinator's turns are coordination, and auto-tasking them looped on the
    # cards it was creating (2026-11-03) -- BUT that must not swallow the owner's
    # own request typed into its pane, which is how the lifecycle failed for bro
    # (prompt_provenance now classifies the hub nudges and agent relays that caused
    # the loop as machinery/agent, so an owner turn reaching here is really his).
    if is_coordinator(agent, tasks) and origin != "owner":
        return None, "this agent coordinates; its work is other agents' tasks, not its own card"
    calls = turn.get("calls", 0)
    span = (turn.get("end") if herdr in ("idle", "done") and turn.get("end") else now) - (turn.get("start") or now)
    # The threshold filters INCIDENTAL activity (a lookup while chatting); it
    # does not decide whether someone asked for something. An attributed owner
    # or agent turn that used a tool did work, however short: one-call owner
    # requests ("check the branch") must still get their lifecycle (task ->
    # ready -> green). Machinery and unattributed turns were refused above.
    trivial = not (calls >= WORK_MIN_TOOL_CALLS or (calls >= 1 and span > WORK_MIN_SPAN_S))
    if trivial and not (origin in ("owner", "agent") and calls >= 1):
        return None, f"trivial so far: {calls} tool call(s), {span:.0f}s (needs {WORK_MIN_TOOL_CALLS}, or 1 and >{WORK_MIN_SPAN_S}s)"
    what = turn.get("said") or untagged(str(turn.get("prompt") or "")) or (f"running {turn['tool']}" if turn.get("tool") else "work")
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


def hub_state(t: Dict) -> Optional[str]:
    """The item's hub state: bro's list carries it as hub_state beside its own
    vocabulary; the hub's list calls it state."""
    return t.get("hub_state") or t.get("state")


def hub_open(t: Dict) -> bool:
    """Open, for display and the invariant: any hub state but done."""
    s = hub_state(t)
    return s in HUB_STATES and s not in HUB_CLOSED


def ready_candidate(t: Dict) -> bool:
    """Auto-ready's set: a state the harness can actually DRIVE to ready, and not
    already ready. A ready item is already green and must never be re-marked.

    Deliberately not `hub_open and not ready`: parked/created/undelivered are
    open for display but the harness has no route to ready from them, so counting
    them as candidates makes them permanently "another open item" - two
    candidates is ambiguity, which silently blocks green for good. An item the
    harness cannot mark must not veto the one it can."""
    return hub_state(t) in READY_ROUTE


def project_items(project: Optional[str], tasks: list) -> list:
    """Readiness is a property of the PROJECT: items match on project + target,
    never on agent or dest (the hub sets neither)."""
    if not project:
        return []
    return [t for t in tasks if t.get("project") == project and t.get("target") in HUB_TARGETS]


def ready_candidates(project: Optional[str], tasks: list) -> list:
    return [t for t in project_items(project, tasks) if ready_candidate(t)]


def item_for_icon(t: Dict) -> Optional[str]:
    """The state an item contributes to the ring.

    An `owner` item that is ready is the thing that earns green: the owner asked
    for it and it is waiting on him. An `agent` item that is ready is progress on
    work nobody asked him about, so it sits BELOW working - visible in the column
    as ready, never turning the ring green. Without this, an agent working on its
    own initiative floods the owner with "ready for your verdict" for work he
    never requested (docs/design-task-provenance.md)."""
    s = hub_state(t)
    if s == "ready" and str(t.get("origin") or "") == "agent":
        return "working"
    return s


def project_icon(row_status: str, project: Optional[str], tasks: list) -> str:
    """The project's ring from its open items: any OWNER-ready item makes it ready."""
    return icon_state(row_status, [item_for_icon(t) for t in project_items(project, tasks) if hub_open(t)])


def is_coordinator(agent: Dict, tasks: list) -> bool:
    """True when THIS agent is its project's coordinator rather than a workhorse.

    Judged by the agent's own role and its own project, never by the list as a
    whole: the previous version asked "is any item anywhere coordinator-targeted",
    which is true for every agent as soon as one project has one coordinator item
    (69 of 100 here), so auto-task was silently disabled workspace-wide and
    nothing the owner said was ever tracked (2026-11-03).

    Evidence: the agent is its project's omp (the coordinator is always an omp,
    the workhorse is its Claude), or it already holds a coordinator item in its
    own project. A Claude pane is a workhorse and keeps the automatic green.
    """
    # role decides, and only role: the owner always runs one omp per project and it IS the coordinator,
    # its Claude is the workhorse. Item history is not evidence about a *different* agent -- a Claude
    # shares its project with its omp, so "a coordinator item exists in my project" is true of both and
    # disabled auto-task for the workhorse too, which is exactly the bug.
    return (agent.get("agent") or agent.get("kind")) == "omp"


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
    # The hub keeps no create note, so the marker above never reaches a hub
    # item; the harness remembers the session it opened the card for instead
    # (Harness.opened). Same rule: only while nobody has moved it since.
    if t.get("session_at") is not None and hub_state(t) == "queued":
        return float(t["session_at"])
    return epoch(last.get("at") or t.get("created"))


def ready_check(agent: Dict, tasks: list, project_busy: List[str], tail: Dict, now: float,
                worker: Optional[Dict] = None) -> Tuple[Optional[Dict], str]:
    """(task to mark ready, why) - or (None, why not). agent is the project's
    settler (its omp, see settler_of); tail is the transcript of whoever did
    the work (worker, see evidence_of). Every condition must hold; each
    guards a way auto-ready could show a false green."""
    if not AUTO_READY:
        return None, "auto-ready off (LIFEVIEW_AUTO_READY=0)"
    project = agent.get("project")
    mine = ready_candidates(project, tasks)
    if not mine:
        return None, f"nothing open in {project or '(no project)'} awaiting ready"
    if len(mine) > 1:
        return None, f"{len(mine)} open items in {project}: ambiguous, left to the agent"
    t = mine[0]
    # who counts as "the agent itself": the settler, the worker, and the hub's
    # role for any agent (hub events carry a role, never a herdr name)
    keys = {agent.get("name"), agent.get("pane_id"), "agent"}
    if worker:
        keys |= {worker.get("name"), worker.get("pane_id")}
    keys -= {None, ""}
    if not AUTO_READY_STARTED and any(h.get("state") == "working" and h.get("by") in keys for h in t.get("history") or []):
        return None, f"{t['id']} was started by the agent itself: `ready` is its call (LIFEVIEW_AUTO_READY_STARTED=1 overrides)"
    if hub_state(t) not in READY_ROUTE:
        return None, f"{t['id']} is {hub_state(t)}: the hub has no harness route from there to ready"
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


def pending(agent: Dict, tasks: list, project_busy: List[str], tail: Dict, now: float,
            worker: Optional[Dict] = None) -> bool:
    """Settling toward auto-ready: not ready now, but would be once the settle
    window has passed with nothing else changing. Every other guard still
    applies, so an agent that won't go green (a question, a task it started,
    no task) is never held."""
    if ready_check(agent, tasks, project_busy, tail, now, worker)[0] is not None:
        return False
    return ready_check(agent, tasks, project_busy, tail, now + SETTLE_S, worker)[0] is not None


def settler_of(group: list) -> Optional[Dict]:
    """The agent a project settles on: its omp (always present, per the owner).
    A project with no omp falls back to its only claude, so it still works;
    several omp (or several claude, no omp) is ambiguous: None."""
    omps = [a for a in group if a.get("agent") == "omp"]
    if omps:
        return omps[0] if len(omps) == 1 else None
    claudes = [a for a in group if a.get("agent") == "claude"]
    return claudes[0] if len(claudes) == 1 else None


def evidence_of(settler: Dict, group: list, t: Optional[Dict], tail_of) -> Dict:
    """Whose transcript the tail check reads: the project's claude when it is
    the one that did the work (the item targets dev, or its transcript moved
    after the item was handed over - better evidence than the omp's), else the
    settler's. A claude is never required."""
    claudes = [a for a in group if a.get("agent") == "claude"]
    if t is None or settler.get("agent") == "claude" or len(claudes) != 1:
        return settler
    c = claudes[0]
    if t.get("target") == "dev":
        return c
    handed, at = task_at(t), tail_of(c).get("at")
    return c if handed is not None and at is not None and at > handed else settler


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
    project = agent.get("project") or project_name(agent)    # World stamps it by the same rule
    if not project:
        return None
    who = agent.get("name") or agent["pane_id"]
    note = (f"opened by the lifeview harness: {who} began work with no task covering it "
            f"(LIFEVIEW_AUTO_TASK=0 disables this) {session_marker(agent, turn)}")
    # origin is WHOSE WORDS started this, not who pressed the button. It was always
    # "harness", so the owner could not tell his own work from an agent's (docs/
    # design-task-provenance.md). The classifier decides once, here; nothing
    # downstream re-derives it.
    origin = prompt_provenance(turn) or "harness"
    if origin == "machinery":
        return None                      # belt and braces: autotask_check already refuses this
    # the card says what was ASKED (the requester's words), not the agent's reply
    if origin in ("owner", "agent") and str(turn.get("prompt") or "").strip():
        title = "auto: " + snippet(untagged(str(turn["prompt"]).strip()) or turn["prompt"], 114)
    got = http_json(HUB_URL + "/api/tasks", {"op": "create", "text": title, "project": project,
                                             "target": "coordinator", "origin": origin, "note": note})
    item = (got or {}).get("item") or {}
    return item.get("id") if item.get("id") else None


def hub_mark_ready(t: Dict, agent: Dict, tail: Dict, quiet: float) -> Optional[Dict]:
    """`by` is the hub's ROLE (owner|agent|harness|bro), never a herdr name -
    the hub refuses anything else. A queued item is started first (by the
    harness, so the event log says so): the hub allows ready only from working."""
    who = agent.get("name") or agent.get("pane_id")
    note = ("auto-marked ready by the lifeview harness: " + str(who) +
            f" settled {quiet:.0f}s after its last answer with this as its one open task; "
            "summary is that answer. LIFEVIEW_AUTO_READY=0 disables this.")
    got: Optional[Dict] = None
    for op in READY_ROUTE.get(hub_state(t) or "", ()):
        body = {"op": op, "id": t["id"], "by": "harness", "note": note}
        if op == "ready":
            body["summary"] = summary_of(tail.get("text", ""))
        got = http_json(HUB_URL + "/api/tasks", body)
        if not got or "error" in got:
            return got                    # refused or down: the caller logs it once
    return got


def resolver_status(project: str) -> Optional[dict]:
    """prescient's authoritative {status, why, rank_table_version} for a project
    (wave 4). Version-gated: an unknown table version is refused, never guessed."""
    got = http_json(PRESCIENT_URL + "/api/tasks/status?project=" + quote(project, safe=""), timeout=3)
    if not isinstance(got, dict):
        return None
    v = got.get("rank_table_version")
    if v != AG_RANK_VERSION:
        log(f"resolver rank_table_version={v!r} != {AG_RANK_VERSION} - ignoring it")
        got = {**got, "stale_table": True}
    return got


def bro_tasks_via_hub() -> Optional[list]:
    got = http_json(HUB_URL + "/api/tasks", timeout=3)
    if not isinstance(got, dict):
        return None
    items = [i for i in got.get("items") or [] if isinstance(i, dict) and i.get("id")]
    for i in items:
        if hub_open(i):
            # the list has no history; auto-ready's guards need it (who started
            # it, when it last moved), so open items get their event log
            ev = http_json(HUB_URL + "/api/tasks/" + quote(i["id"], safe=""), timeout=3) or {}
            i["history"] = [{"at": e.get("at"), "state": e.get("to_state"), "by": e.get("by"), "note": e.get("note")}
                            for e in ev.get("events") or [] if isinstance(e, dict)]
    return items


def open_task(agent: Dict, title: str, turn: Dict) -> Optional[str]:
    """`bro task add` for the agent, left `sent` (it may still `start` it).
    By the harness, so auto-ready's started-by-the-agent exclusion never
    applies. Returns the new task id, or None."""
    if TASK_HUB == "prescient" and hub_available():
        return hub_open_task(agent, title, turn)
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
    return project_of_root(git_root(str(agent.get("cwd") or "")))


def project_of_root(root: Optional[str]) -> Optional[str]:
    # The board's rule (prescient's gantt.agent.project_of): the repo folder's
    # name with a leading dot dropped -- `.dotfiles` is "dotfiles". Matching it
    # is what keeps one project from splitting into two on the hub.
    return (os.path.basename(root).lstrip(".") or None) if root else None


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

    def __init__(self, agents: Optional[list] = None, root_of=None) -> None:
        self.agents = [a for a in (list_agents() if agents is None else agents) if a.get("pane_id")]
        self.live = {a["pane_id"] for a in self.agents}
        roots: Dict[str, Optional[str]] = {}
        self.root: Dict[str, Optional[str]] = {}
        for a in self.agents:
            cwd = a.get("cwd") or ""
            if cwd not in roots:
                roots[cwd] = (root_of or git_root)(cwd)
            self.root[a["pane_id"]] = roots[cwd]
            a["project"] = project_of_root(roots[cwd])     # what auto-ready matches items on

    def projects(self) -> Dict[str, list]:
        out: Dict[str, list] = {}
        for a in self.agents:
            if a.get("project"):
                out.setdefault(a["project"], []).append(a)
        return out

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
        self.opened: Dict[str, float] = {}    # card id -> start of the session it was opened for (see task_at)

    def tick(self) -> None:
        w = World()
        tasks = bro_tasks() if (AUTO_READY or AUTO_TASK) else None
        self.annotate(tasks)
        self.auto_task(w, tasks)
        tails: Dict[str, Dict] = {}       # pane -> its OWN transcript tail (also the status lines' source)
        plans = self.ready_plans(w, tasks, tails)
        # Mark ready BEFORE the status write: the hold is released only once
        # the task is green, so no board read can land between the two.
        self.auto_ready(w, tasks, plans)
        now = time.time()
        holds = frozenset(p["settler"]["pane_id"] for p in plans.values()
                          if pending(p["settler"], tasks or [], w.project_busy(p["settler"]), p["tail"], now, p["worker"]))

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

    def annotate(self, tasks: Optional[list]) -> None:
        """Re-attach what the hub doesn't keep: the session each card this
        run opened was opened for (task_at counts that session's answer)."""
        for t in tasks or []:
            if t.get("id") in self.opened:
                t["session_at"] = self.opened[t["id"]]

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
                if turn.get("start") is not None:
                    self.opened[tid] = float(turn["start"])
                tasks.append({"id": tid, "state": "sent", "agent": who, "dest": f"agent:{who}",
                              "hub_state": "queued", "project": a.get("project"), "target": "coordinator",
                              "origin": prompt_provenance(turn), "session_at": self.opened.get(tid),
                              "history": [{"at": datetime.now().astimezone().isoformat(timespec="seconds"),
                                           "state": "sent", "by": HARNESS_BY, "note": marker}]})
            else:
                log(f"auto-task for {who} failed (bro CLI: {bro_bin() or 'not found'})")

    @staticmethod
    def ready_plans(w: World, tasks: Optional[list], tails: Dict[str, Dict]) -> Dict[str, Dict]:
        """Per project with something open: {settler, worker, path, tail}. The
        project settles on its omp; the tail is read from the worker's
        transcript (evidence_of). Transcripts are read only for projects with
        a candidate; every read lands in tails, keyed by the reader's pane."""
        out: Dict[str, Dict] = {}
        if not tasks:
            return out
        paths: Dict[str, Optional[Path]] = {}

        def own_tail(a: Dict) -> Dict:
            if a["pane_id"] not in tails:
                paths[a["pane_id"]] = path = transcript_of(a, w.agents)
                tails[a["pane_id"]] = scan_tail(path) if path else {"verdict": None, "at": None, "text": ""}
            return tails[a["pane_id"]]

        for project, group in w.projects().items():
            cands = ready_candidates(project, tasks)
            settler = settler_of(group) if cands else None
            if not settler:
                continue
            worker = evidence_of(settler, group, cands[0] if len(cands) == 1 else None, own_tail)
            tail = own_tail(worker)
            out[project] = {"settler": settler, "worker": worker, "path": paths.get(worker["pane_id"]), "tail": tail}
        return out

    def auto_ready(self, w: World, tasks: Optional[list], plans: Dict[str, Dict]) -> None:
        if not AUTO_READY or tasks is None:
            return                        # off, or bro down: nothing to mark
        now = time.time()
        for p in plans.values():
            a, tail = p["settler"], p["tail"]
            t, why = ready_check(a, tasks, w.project_busy(a), tail, now, p["worker"])
            if t is None:
                continue
            got = mark_ready(t, a, tail, now - tail["at"])
            who = a.get("name") or a["pane_id"]
            if got and (got.get("task") or got.get("item") or {}).get("state") == "ready":   # bro answers task, the hub item
                log(f"{t['id']} -> ready (auto) for {a.get('project')} via {who}: {why}")
                t["state"] = "ready"          # this tick's copy: not again
                t.pop("hub_state", None)
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
    plans = Harness.ready_plans(w, tasks, {})
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
        mine = project_items(a.get("project"), tasks or [])   # the project's items: readiness is not the agent's
        row = rows.get(name) or {}
        status = row.get("status") or (e.get("state") if isinstance(e, dict) else None) or herdr
        relevant = [t["state"] for t in mine if t.get("state") not in ("done", "dropped")]
        # prescient's answer is PER PROJECT, and this loop draws a per-AGENT icon: showing it on every
        # row made an idle omp read "working" because its project's Claude was busy. Only the row the
        # resolver actually named may claim it; every other row keeps its own state.
        resolved = resolver_status(root.rsplit("/", 1)[-1].lstrip(".")) if root else None
        if (resolved and not resolved.get("stale_table") and resolved.get("status")
                and resolved.get("agent") == name):
            icon = resolved["status"]
            resolved_from = f"prescient, for {resolved.get('agent')}"
        else:
            icon = icon_state(status, relevant + [hub_state(t) for t in project_items(a.get("project"), tasks or [])
                                                  if hub_open(t)])
            resolved_from = None
        print(f"\n{name} [{a['pane_id']}, {a.get('agent')}] -> icon: {icon}"
              + (f"  (from {resolved_from})" if resolved_from else ""))
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
            p = plans.get(a.get("project") or "")
            if not p:
                print("  auto-ready: " + ready_check(a, tasks, w.project_busy(a), tail, now)[1])
            elif p["settler"] is a:
                src = p["worker"].get("name") or p["worker"]["pane_id"]
                print(f"  auto-ready ({a.get('project')}, tail from {src}"
                      f"{': ' + p['path'].name if p['path'] else ''}): "
                      + ready_check(a, tasks, w.project_busy(a), p["tail"], now, p["worker"])[1])
            else:
                print(f"  auto-ready: {a.get('project')} settles on {p['settler'].get('name') or p['settler']['pane_id']}")
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
