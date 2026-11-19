# TASK: `workspace-up` must never kill a process that only *mentions* a piece

Found by the worker in `docs/task-workspace-up-lockholder.md` (27 tests OK, fix verified).
It cost them two shell kills and lost output; they contained it with `repro.sh` and noted
"a stricter match (for example, only processes whose argv[0] is a Python) is" the fix.

**It is not a testing annoyance. It is an owner-visible hazard.**

## The bug

`scripts/workspace-up`

- pieces match `re.search(p.match, x.command)` over **the whole command line**;
- `stop()` is `os.kill(proc.pid, SIGTERM)` then `SIGKILL` — no process-group check, no
  self-exclusion, no argv check.

So any process whose *command line contains the pattern* is a candidate to be killed:

- a shell where the owner types `pgrep -f 'lifeview.py --daemon'` — killed (observed, twice);
- `workspace-up`'s own invoking shell, if it was launched as part of a command line that names
  a piece (`./scripts/workspace-up --only lifeview` does **not** name one, but
  `bash -c '… lifeview.py --daemon …'` does);
- an editor or `tail -f` holding the pattern in its argv;
- a `git commit -m "fix lifeview.py --daemon lock"` — the message is in the command line.

Because `stop()` escalates to `SIGKILL` after 10 s, a false match is unrecoverable and, for a
shell, takes its children with it.

## Fix

Two independent guards. Both are required — the first alone still kills a non-shell process
that merely mentions the pattern, and the second alone does not fix the owner's terminal.

### 1. Match the *program*, not the command line

A piece is a process **running** that program. Require the match to be on the executed
program, not anywhere in the arguments:

- for a Python piece, the process's argv must be an interpreter whose first argument (after
  `-` flags) is the piece's script path — e.g. `python3 …/lifeview.py --daemon`, not
  `zsh -c "… lifeview.py --daemon …"`;
- implement by parsing argv from the process table into `argv[0]` and the rest, and requiring
  `argv[0]` to basename-match an interpreter (or the script itself) **and** the script path to
  appear as a *whole argv element*, anchored (`^(?:.*/)?lifeview\.py$`) — never as a
  substring of a joined string;
- keep the existing `Piece.match` as a fast prefilter if you like, but the decision must come
  from the argv rule.

### 2. Never signal ourselves, our ancestors, or our session

Even with a correct match, `workspace-up` must refuse to signal:

- its own pid;
- any ancestor pid (walk `ps` parent links up from `os.getpid()`);
- any process in the same process group / session as the invoker.

If a candidate is excluded on this basis, **print that** — `lifeview: skipping pid N (our own
ancestor)` — rather than silently ignoring it, so a real piece misidentified as an ancestor is
visible.

## Acceptance

1. **A shell that only mentions a piece is not matched.** Prove it: run
   `workspace-up --dry` from a command line that contains `lifeview.py --daemon` (e.g.
   `bash -c 'echo lifeview.py --daemon; ./scripts/workspace-up --dry --only lifeview'`) and
   show it neither restarts nor names the invoking shell. It must still identify the real
   daemon.
2. The real daemon is still matched and restarted when stale — the `docs/task-workspace-up-lockholder.md`
   behaviour must not regress (lock holder judged, in-flight launch named).
3. `--dry` from the coordinator's own pane (a non-shell invocation) reports `0 stale` when
   everything is healthy and kills nothing.
4. Ancestor/self exclusion is unit-tested: a fake process table where the only match is the
   current process or its parent yields no actions.
5. `python3 scripts/test_workspace_up.py` green, with new cases named for the shell case.
6. Re-run the full `workspace-up` and paste the output — expect `0 restarted`, `6 running`.

## Rules

- Do not weaken the staleness logic fixed in the previous spec; this only constrains **who may
  be signalled**.
- Do not special-case any piece by name.
- Keep `repro.sh` and mention in the report whether it is still needed.
- Commit locally. Do not push.
