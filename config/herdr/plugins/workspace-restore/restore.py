#!/usr/bin/env python3
"""Bring every project tab back to the owner's shape: nvim+omp left, claude right.

Why this exists: herdr restores a pane as a plain shell in its saved cwd, and
~/.zshrc (the "herdr re-entry" block) does `exec nvim` in any herdr shell whose
cwd has a .conda-env. So after a server restart BOTH panes of a project tab come
back as a bare nvim: no omp on the left, and no shell on the right for
`herdr agent start` to take ("pane is not an available shell").

What it does, per project tab (1 or 2 side-by-side panes, left cwd is a\nrepo, a .conda-env project, or a directory omp has a session for):
  left   has an agent            -> ok
         nvim without a terminal -> ctrl+a (opens the omp REPL)
         idle shell              -> run nvim, then ctrl+a
  right  has an agent            -> ok
         idle shell              -> herdr agent start claude
         idle nvim               -> replaced: split it with HERDR_NO_NVIM=1 (a
                                    real shell), start claude there, close the nvim
                                    (idle = no unsaved buffer, no terminal: the
                                    restored state; its files stay in the session)
         nvim with unsaved work
         or a terminal           -> left alone
         absent                  -> left alone; created only with --create-missing

Work projects (cwd under the work tree) never get a claude pane, not even with
--create-missing: the owner runs no claude workhorse there. Their left pane is
restored like any other.

The owner-closed choice: a pane that does not exist is never created
automatically. herdr restores the layout the owner left, so a missing right pane
means he closed it; only an existing-but-empty pane is filled. `--create-missing`
is the explicit, by-hand way to add one.

`--startup` (the plugin's [[startup]] hook, once per server start) first runs
scripts/workspace-up, so the services come up with the panes.

Everything else is left alone: tabs with 3+ panes or stacked panes, non-project
tabs, panes running any other foreground command. It never changes herdr config.
Idempotent: a second run prints `ok` for every pane and does nothing.
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

HERDR_BIN = os.environ.get("HERDR_BIN_PATH", "herdr")
STATE_DIR = Path(os.environ.get("HERDR_PLUGIN_STATE_DIR")
                 or Path.home() / ".local/state/herdr/plugins/dotfiles.workspace-restore")
SHELLS = {"zsh", "bash", "fish", "sh"}
PROJECT_MARKERS = (".git", ".conda-env")
# Work projects get nvim+omp only: the owner runs no claude workhorse there
# (owner rule 2026-11-12; he closed the one this script had opened). Same bare
# scope marker as the omp scope extensions.
WORK_MARKER = "Desktop/tallence"
OMP_SESSIONS = Path.home() / ".omp" / "agent" / "sessions"
WORKSPACE_UP = Path(__file__).resolve().parents[4] / "scripts" / "workspace-up"
# nvim here auto-loads a per-directory session, so a freshly restored nvim already
# lists files: "empty" cannot mean "no buffers". What matters is what closing
# it would lose: unsaved edits in a file buffer, or a running terminal.
NVIM_PROBE = ('json_encode({"unsaved":len(filter(getbufinfo(),{_,b->b.changed&&getbufvar(b.bufnr,"&buftype")==""})),'
              '"terms":len(filter(getbufinfo(),{_,b->getbufvar(b.bufnr,"&buftype")=="terminal"}))})')


class HerdrError(RuntimeError):
    pass


def herdr(*args: str, timeout: int = 40) -> dict:
    try:
        proc = subprocess.run([HERDR_BIN, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HerdrError(f"herdr {' '.join(args[:2])}: {exc}") from exc
    if proc.returncode == 0 and not proc.stdout.strip():
        return {}  # e.g. `pane run`, `pane send-keys`: success without a body
    try:
        payload = json.loads(proc.stdout or proc.stderr)
    except ValueError as exc:
        raise HerdrError(f"herdr {' '.join(args[:2])}: {(proc.stderr or proc.stdout).strip()[:200]}") from exc
    if proc.returncode != 0 or "error" in payload:
        err = payload.get("error", payload)
        raise HerdrError(f"{err.get('code', 'error')}: {err.get('message', err)}")
    return payload.get("result", {})


# ---------------------------------------------------------------- observation

def nvim_state(tui_pid: int) -> Optional[dict]:
    """Buffer counts of the nvim whose TUI process is tui_pid, over its RPC socket
    (read-only). The socket belongs to the `nvim --embed` child. None = unknown."""
    try:
        kids = subprocess.run(["pgrep", "-P", str(tui_pid)], capture_output=True, text=True,
                              timeout=5).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        return None
    tmp = os.environ.get("TMPDIR") or tempfile.gettempdir()
    for pid in [*kids, str(tui_pid)]:
        for sock in glob.glob(os.path.join(tmp, "nvim.*", "*", f"nvim.{pid}.0")):
            try:
                out = subprocess.run(["nvim", "--server", sock, "--remote-expr", NVIM_PROBE],
                                     capture_output=True, text=True, timeout=5)
                return json.loads(out.stdout)
            except (OSError, subprocess.TimeoutExpired, ValueError):
                continue
    return None


def observe_pane(pane: dict) -> dict:
    """kind: agent | shell | nvim | busy | unknown (+ nvim buffer state)."""
    info = {"pane_id": pane["pane_id"], "cwd": pane.get("cwd") or "", "agent": pane.get("agent"),
            "kind": "unknown", "nvim": None}
    if info["agent"]:
        info["kind"] = "agent"
        return info
    try:
        pi = herdr("pane", "process-info", "--pane", pane["pane_id"])["process_info"]
    except HerdrError:
        return info
    fg = pi.get("foreground_processes") or []
    if not fg:
        return info
    names = {(p.get("argv0") or p.get("name") or "").rsplit("/", 1)[-1].lstrip("-") for p in fg}
    if names == {"nvim"}:
        info["kind"] = "nvim"
        info["nvim"] = nvim_state(fg[0]["pid"])
    elif len(fg) == 1 and names <= SHELLS and fg[0].get("pid") == pi.get("shell_pid"):
        info["kind"] = "shell"
    else:
        info["kind"] = "busy"
    return info


def is_project(cwd: str) -> bool:
    """A repo/conda project, or any directory omp has already worked in (omp
    keeps one session dir per cwd, named after the home-relative path)."""
    if not cwd:
        return False
    if any(os.path.exists(os.path.join(cwd, m)) for m in PROJECT_MARKERS):
        return True
    try:
        rel = Path(cwd).resolve().relative_to(Path.home().resolve())
    except ValueError:
        return False
    return bool(rel.parts) and (OMP_SESSIONS / ("-" + "-".join(rel.parts))).is_dir()


def snapshot() -> List[dict]:
    """Every tab with its panes ordered left to right."""
    tabs = []
    for ws in herdr("workspace", "list")["workspaces"]:
        wid = ws["workspace_id"]
        by_tab: Dict[str, List[dict]] = {}
        for pane in herdr("pane", "list", "--workspace", wid)["panes"]:
            by_tab.setdefault(pane["tab_id"], []).append(pane)
        for tab in herdr("tab", "list", "--workspace", wid)["tabs"]:
            panes = by_tab.get(tab["tab_id"], [])
            if not panes:
                continue
            layout = herdr("pane", "layout", "--pane", panes[0]["pane_id"])["layout"]
            rects = {p["pane_id"]: p["rect"] for p in layout["panes"]}
            observed = []
            for pane in panes:
                o = observe_pane(pane)
                o["rect"] = rects.get(pane["pane_id"], {"x": 0, "y": 0})
                observed.append(o)
            observed.sort(key=lambda o: (o["rect"]["x"], o["rect"]["y"]))
            cwd = observed[0]["cwd"]
            tabs.append({"tab_id": tab["tab_id"], "label": tab.get("label") or "", "panes": observed,
                         "project": is_project(cwd), "work": WORK_MARKER in cwd})
    return tabs


# ------------------------------------------------------------------- planning

def disposable(nvim: Optional[dict]) -> bool:
    """Closing this nvim loses nothing: no unsaved file buffer, no terminal.
    Unknown state (no socket answer) is never disposable."""
    return bool(nvim) and not (nvim["unsaved"] or nvim["terms"])


def plan(tabs: List[dict], create_missing: bool = False) -> List[dict]:
    """Pure: observed tabs -> one step per line of output. `do` is None when
    there is nothing to change."""
    steps: List[dict] = []

    def step(target, role, do, note, **extra):
        steps.append({"target": target, "role": role, "do": do, "note": note, **extra})

    for tab in tabs:
        panes = tab["panes"]
        if not tab["project"]:
            step(tab["tab_id"], "-", None, "not a project tab, left alone")
            continue
        if len(panes) > 2 or (len(panes) == 2 and panes[0]["rect"]["x"] == panes[1]["rect"]["x"]):
            step(tab["tab_id"], "-", None, "custom layout, left alone")
            continue
        left = panes[0]
        right = panes[1] if len(panes) == 2 else None

        if left["kind"] == "agent":
            step(left["pane_id"], left["agent"], None, "ok")
        elif left["kind"] == "nvim":
            if left["nvim"] and left["nvim"]["terms"]:
                step(left["pane_id"], "omp", None, "nvim already has a terminal, left alone")
            else:
                step(left["pane_id"], "omp", "open_repl", "started")
        elif left["kind"] == "shell":
            step(left["pane_id"], "omp", "nvim_then_repl", "started")
        else:
            step(left["pane_id"], "omp", None, f"{left['kind']} foreground, left alone")

        if tab.get("work"):
            if right is not None and right["kind"] == "agent":
                step(right["pane_id"], right["agent"], None, "ok")
            else:
                step(right["pane_id"] if right else tab["tab_id"], "claude", None,
                     "work project: no claude pane, by owner rule")
        elif right is None:
            if create_missing:
                step(tab["tab_id"], "claude", "create", "created", left=left["pane_id"], cwd=left["cwd"])
            else:
                step(tab["tab_id"], "claude", None, "no right pane (closed by owner), left alone; "
                                                    "--create-missing adds one")
        elif right["kind"] == "agent":
            step(right["pane_id"], right["agent"], None, "ok")
        elif right["kind"] == "shell":
            step(right["pane_id"], "claude", "start_claude", "started")
        elif right["kind"] == "nvim":
            if disposable(right["nvim"]):
                step(right["pane_id"], "claude", "replace", "replaced idle nvim", cwd=right["cwd"] or left["cwd"])
            else:
                step(right["pane_id"], "claude", None, "nvim with unsaved changes or a terminal (or unreadable), left alone")
        else:
            step(right["pane_id"], "claude", None, f"{right['kind']} foreground, left alone")
    return steps


# ------------------------------------------------------------------ execution

def wait_for(pred, timeout: float, every: float = 1.0):
    deadline = time.time() + timeout
    while True:
        try:
            value = pred()
        except HerdrError:
            value = None
        if value or time.time() >= deadline:
            return value
        time.sleep(every)


def pane_agent(pane_id: str) -> Optional[str]:
    return herdr("pane", "get", pane_id).get("pane", {}).get("agent")


def pane_kind(pane_id: str) -> str:
    return observe_pane({"pane_id": pane_id})["kind"]


def open_repl(pane_id: str) -> str:
    herdr("pane", "send-keys", pane_id, "ctrl+a")
    return "started" if wait_for(lambda: pane_agent(pane_id), 60, 2) else "sent ctrl+a, omp not detected yet"


def nvim_then_repl(pane_id: str) -> str:
    herdr("pane", "run", pane_id, "nvim")
    if not wait_for(lambda: pane_kind(pane_id) == "nvim", 20):
        raise HerdrError("nvim did not come up")
    time.sleep(2)  # plugins load before the keymap exists
    return open_repl(pane_id)


def start_claude(pane_id: str) -> str:
    # claude-name renames it to claude-v<config>-<pane> on its next tick.
    name = "claude-" + pane_id.replace(":", "").lower()
    try:
        herdr("agent", "start", name, "--kind", "claude", "--pane", pane_id, timeout=60)
    except HerdrError as exc:
        if "agent_not_ready" in str(exc):
            return "started, waiting at a startup dialog"
        raise
    return "started"


def shell_split(of_pane: str, cwd: str) -> str:
    """A real shell pane to the right of of_pane: HERDR_NO_NVIM=1 keeps zshrc
    from exec'ing nvim, so `agent start` can take it."""
    args = ["pane", "split", "--pane", of_pane, "--direction", "right", "--env", "HERDR_NO_NVIM=1", "--no-focus"]
    if cwd:
        args += ["--cwd", cwd]
    new = herdr(*args)["pane"]["pane_id"]
    if not wait_for(lambda: pane_kind(new) == "shell", 20):
        raise HerdrError(f"{new} did not reach a shell prompt")
    return new


def execute(step: dict) -> str:
    do, target = step["do"], step["target"]
    if do == "open_repl":
        return open_repl(target)
    if do == "nvim_then_repl":
        return nvim_then_repl(target)
    if do == "start_claude":
        return start_claude(target)
    if do == "create":
        new = shell_split(step["left"], step["cwd"])
        return f"created {new}, claude {start_claude(new)}"
    if do == "replace":
        new = shell_split(target, step["cwd"])
        result = start_claude(new)
        # Re-check right before the only destructive call.
        again = observe_pane({"pane_id": target})
        if again["kind"] == "nvim" and disposable(again["nvim"]):
            herdr("pane", "close", target)
            return f"replaced idle nvim with {new}, claude {result}"
        return f"claude {result} in {new}; {target} changed meanwhile, not closed"
    raise HerdrError(f"unknown step {do}")


def settle(timeout: float = 90) -> None:
    """Server start: wait until the restored panes stopped changing (shells have
    exec'd into nvim, nvim answers on its socket) before deciding anything."""
    deadline, last, stable = time.time() + timeout, None, 0
    time.sleep(5)
    while time.time() < deadline:
        try:
            tabs = snapshot()
        except HerdrError:
            tabs = []
        sig = [(p["pane_id"], p["kind"], p["nvim"] is not None) for t in tabs for p in t["panes"]]
        ready = sig and all(k != "unknown" and (k != "nvim" or has) for _, k, has in sig)
        stable = stable + 1 if ready and sig == last else 0
        if stable >= 2:
            return
        last = sig
        time.sleep(2)


def services() -> None:
    """scripts/workspace-up: start/refresh prescient, bro, the life-view daemon
    and the discord bot. Idempotent on its own; its report goes to the log."""
    try:
        # Without this plugin's HERDR_PLUGIN_* vars: workspace-up reads
        # HERDR_PLUGIN_STATE_DIR to find the discord bot's log, and ours is not it.
        env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_PLUGIN_")}
        proc = subprocess.run([sys.executable, str(WORKSPACE_UP)], capture_output=True, text=True,
                              timeout=300, env=env)
        out = proc.stdout + proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        out = f"workspace-up did not run: {exc}\n"
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(STATE_DIR / "restore.log", "a") as log:
        log.write("".join(f"{stamp} [startup] {line}\n" for line in out.splitlines()))


def run(args) -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = open(STATE_DIR / "restore.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another restore is running; nothing done")
        return 0
    if args.startup:
        time.sleep(5)  # let the other plugins' own startup hooks take their locks first
        services()
        settle()
    failed = 0
    lines = []
    tabs = [t for t in snapshot() if not args.tab or t["tab_id"] in args.tab]
    for step in plan(tabs, create_missing=args.create_missing):
        note = step["note"]
        if step["do"]:
            if args.dry_run:
                note = f"would: {step['do']}"
            else:
                try:
                    note = execute(step)
                except HerdrError as exc:
                    failed += 1
                    note = f"FAILED ({exc})"
        line = f"{step['target']:<8}{step['role']:<8}{note}"
        lines.append(line)
        print(line, flush=True)
    with open(STATE_DIR / "restore.log", "a") as log:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        mode = "startup" if args.startup else "manual"
        log.write("".join(f"{stamp} [{mode}] {line}\n" for line in lines))
    return 1 if failed else 0


def daemonize() -> None:
    """The startup hook is one-shot; detach so the restore outlives it."""
    if os.fork():
        os._exit(0)
    os.setsid()
    if os.fork():
        os._exit(0)
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--create-missing", action="store_true",
                    help="also create a claude pane in project tabs that have no right pane")
    ap.add_argument("--tab", action="append", metavar="TAB_ID", help="only this tab (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="print what would change, change nothing")
    ap.add_argument("--startup", action="store_true",
                    help="the herdr [[startup]] hook: detach, run scripts/workspace-up (services), wait for "
                         "the restored panes to settle, then restore; everything is logged to restore.log")
    args = ap.parse_args()
    if args.startup:
        daemonize()
    try:
        return run(args)
    except HerdrError as exc:
        print(f"herdr-restore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
