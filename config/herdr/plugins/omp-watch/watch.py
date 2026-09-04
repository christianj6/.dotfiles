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
   (idle) or not (working) -- with no time-based staleness window needed:
   an unfinished-turn entry means "working" even if the model has been
   thinking silently for a while, and a stale-but-still-open REPL's last
   entry is simply whatever it left off at, which is correctly idle.

Reports via the documented custom-integration CLI pattern:
https://herdr.dev/docs/integrations/#integrate-your-own-agent

Honest scope: there is no reliable "needs your approval" (blocked) signal in
the transcript -- approval prompts are UI-only and are not logged. This
reports working/idle only. Revisit if a future omp version logs approval
events.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

POLL_SECONDS = 3
TAIL_BYTES = 32_000
SOURCE = "custom:omp-watch"
AGENT = "omp"
HOME = Path.home()
SESSIONS_DIR = HOME / ".omp" / "agent" / "sessions"
# Plugins should call herdr through HERDR_BIN_PATH, not a bare "herdr" on
# PATH: https://herdr.dev/docs/plugins/
HERDR_BIN = os.environ.get("HERDR_BIN_PATH", "herdr")


def session_key(cwd: str) -> str:
    """Mirror scripts/projects/omp-last's cwd -> session-dir-name transform."""
    home_str = str(HOME)
    suffix = cwd[len(home_str):] if cwd.startswith(home_str) else cwd
    return suffix.replace("/", "-")


def newest_session_file(cwd: str) -> Optional[Path]:
    key = session_key(cwd)
    if not key:
        return None
    d = SESSIONS_DIR / key
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def tail_entries(path: Path, nbytes: int = TAIL_BYTES) -> List[dict]:
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > nbytes:
            f.seek(size - nbytes)
            f.readline()  # drop a possibly-truncated partial first line
        raw = f.read()
    entries = []
    for line in raw.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def infer_state(entries: List[dict]) -> Optional[str]:
    """Walk the tail in order, deriving a coarse working/idle/exit verdict
    from the last recognizable entry. Unrecognized entries never change the
    running verdict -- conservative by construction."""
    verdict: Optional[str] = None
    for e in entries:
        etype = e.get("type")
        # role lives at entry.message.role, not top-level -- confirmed
        # empirically 2026-09-04 against a real session file; the earlier
        # top-level e.get("role") always returned None, so the user/
        # assistant/toolResult branches below never actually matched.
        role = (e.get("message") or {}).get("role")
        if etype == "custom" and e.get("customType") == "session_exit":
            verdict = "exit"
        elif etype == "custom" and e.get("customType") == "tool_execution_start":
            verdict = "working"
        elif etype in ("toolCall", "function_call"):
            verdict = "working"
        elif etype == "message" and role == "user":
            verdict = "working"
        elif etype == "message" and role == "toolResult":
            verdict = "working"  # the agent loop still has to react to it
        elif etype == "message" and role == "assistant":
            verdict = "idle"  # a finished assistant reply ends the turn
    return verdict


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


def live_omp_cwds() -> Dict[str, int]:
    """{cwd: pid} for every running omp process, matched by resolved argv
    basename (covers both a direct `omp ...` invocation and the
    `bun .../bin/omp ...` shape this machine actually uses)."""
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,command="], capture_output=True, text=True, timeout=10
    )
    result: Dict[str, int] = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_str, _, cmd = line.partition(" ")
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        tokens = cmd.split()
        if not any(Path(t).name == "omp" for t in tokens if not t.startswith("-")):
            continue
        cwd = process_cwd(pid)
        if cwd:
            result[cwd] = pid
    return result


def run_herdr(*args: str) -> None:
    try:
        subprocess.run([HERDR_BIN, *args], check=False, capture_output=True, timeout=10)
    except Exception as exc:  # keep the watcher alive across any CLI hiccup
        print(f"[omp-watch] herdr call failed {args}: {exc}", file=sys.stderr)


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


def main() -> None:
    parent_pid_at_start = os.getppid()
    last_state: Dict[str, str] = {}
    seq: Dict[str, int] = {}

    def next_seq(pane_id: str) -> int:
        seq[pane_id] = seq.get(pane_id, 0) + 1
        return seq[pane_id]

    def release(pane_id: str) -> None:
        if last_state.pop(pane_id, None) is not None:
            run_herdr("pane", "release-agent", pane_id, "--source", SOURCE, "--agent", AGENT)

    while True:
        # herdr's [[startup]] hook has no supervision and sends this
        # process no signal when its owning server shuts down (verified
        # empirically 2026-09-04: three successive server restarts each
        # left a fully orphaned watcher running under init -- multiple
        # instances silently accumulated and fought over the same panes,
        # which is exactly why a newly opened pane in another workspace
        # stayed stuck on "unknown"). A dead parent reparents us; exit for
        # good the instant that happens -- the new server spawns its own
        # fresh instance, and this one must not linger to duplicate it.
        if os.getppid() != parent_pid_at_start:
            print(
                f"[omp-watch] orphaned (parent {parent_pid_at_start} -> {os.getppid()}); exiting for good",
                file=sys.stderr,
            )
            sys.exit(0)

        try:
            live = live_omp_cwds()
            for pane in load_panes():
                pane_id = pane["pane_id"]
                cwd_raw = pane.get("cwd", "")
                # omp names its session directory from the shell's logical
                # cwd, but a live process's cwd as reported by lsof/procfs
                # is always fully symlink-resolved (e.g. macOS's
                # /tmp -> /private/tmp, or any symlinked project dir) --
                # resolve a second copy so presence-matching isn't silently
                # broken by a symlink, without breaking the session-file
                # lookup (which must stay keyed on the raw/logical path).
                cwd_resolved = str(Path(cwd_raw).resolve()) if cwd_raw else ""

                if cwd_resolved not in live:
                    release(pane_id)
                    continue

                # Present -> at least idle. Only upgrade to "working" when
                # the transcript's last entry represents an unfinished turn;
                # no file yet (never used) or a finished last entry both
                # mean idle. No staleness window: a long model-thinking
                # pause with no new bytes is still correctly "working".
                verdict = "idle"
                sfile = newest_session_file(cwd_raw)
                if sfile is not None:
                    tail_verdict = infer_state(tail_entries(sfile))
                    if tail_verdict == "working":
                        verdict = "working"

                if last_state.get(pane_id) == verdict:
                    continue

                report_args = [
                    "pane", "report-agent", pane_id,
                    "--source", SOURCE, "--agent", AGENT, "--state", verdict,
                    "--seq", str(next_seq(pane_id)),
                ]
                if sfile is not None:
                    report_args += ["--agent-session-path", str(sfile)]
                run_herdr(*report_args)
                last_state[pane_id] = verdict
        except Exception as exc:  # never let one bad tick kill the watcher
            print(f"[omp-watch] tick error: {exc}", file=sys.stderr)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
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
