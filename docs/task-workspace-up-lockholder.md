# TASK: `workspace-up` judges staleness against a doomed hook launch, never restarting the real daemon

Found by the worker while deploying `docs/task-ready-does-not-cover.md`; flagged, not fixed
(out of that spec's scope). The diagnosis is correct — verified in the code below.

## The bug

`scripts/workspace-up:423`

```python
proc = max(procs, key=lambda x: x.started)     # the NEWEST matching process
if code_m > proc.started + 1:
    ... restart
```

Every `[[events]]` hook fires `python3 lifeview.py --daemon`, which is a **short-lived launch
that exits on the singleton lock**. While such a launch is in flight, it is the newest match,
so:

- `proc.started` is *now*, so `code_m > proc.started + 1` is false;
- the real, stale daemon (an older pid, the **lock holder**) is never examined;
- `workspace-up` prints `running (pid <doomed>) up 0s` and skips the restart.

Observed live: `workspace-up --only lifeview` reported `running (pid 54127) up 0s` while the
actual daemon was pid 20359 on stale code. The worker restarted it by hand.

**This is the same class as `docs/task-fix-duplicate-tasks.md`**: a check that reports health
without examining the thing that matters. It also silently degrades the omp-staleness feature
and the service restarts generally, since the same `max(procs, key=started)` serves every piece.

## Fix

**Judge the process that actually serves, not the newest match.**

- The singleton lock holds the serving pid (`~/.local/state/herdr/plugins/<plugin-id>/lock` —
  see `config/herdr/plugins/_shared/singleton.py`). For a piece that has a lock, read the pid
  from the lock and use *that* process for the staleness comparison.
- Generalise without over-fitting: add an optional `serving()` hook to `Piece` that returns the
  authoritative pid(s) for that piece, defaulting to today's `procs`.
  - `lifeview`, `discord-bot`, `omp-watch`, `claude-name` → the pid in the lock file (verify it
    is alive and matches the piece's regex; if the lock is missing or names a dead pid, fall
    back to `procs` and say so in the line).
  - `prescient`, `bro` — no lock; keep `procs`.
- **Restart all matches, not just the newest** — the existing code already does `for x in
  procs: stop(x)`; keep that, then start. A hook launch in flight will exit on its own, but
  stopping it too is harmless and avoids a race where it wins the lock after the restart.
- **Name the case in the output** so it is visible rather than clever: if the newest match is
  not the serving pid, say so — e.g. `running (pid 20359 lock holder; 54127 launch in flight)`.

## Acceptance

1. **Reproduce first, then fix.** With the daemon serving on stale code and a hook launch
   in flight, `workspace-up --only lifeview` must **restart** the serving daemon, not skip it.
   Show the before/after, including the pid it chose and why.
2. `workspace-up` with everything healthy still reports `0 stale, 0 restarted` and does not
   restart anything (no thrash).
3. A lock file naming a **dead** pid falls back to the process list and does not crash.
4. A piece with no lock (`prescient`, `bro`) behaves exactly as before.
5. `--dry` says `would restart` with the same reasoning it would act on.
6. Tests: the selection logic must be testable without a live daemon — factor the "which pid
   serves" choice into a function and unit-test (lock holder preferred; newest fallback;
   dead-pid fallback). Keep the existing harness/tests green.

## Rules

- `workspace-up` is the piece that keeps the workspace honest; **do not add a special case for
  lifeview only** — every locked piece gets the same treatment or the next plugin regresses
  silently.
- Do not change what counts as "stale" (code mtime vs process start); only **which process** is
  judged.
- Do not touch prescient's store, and do not re-flip `TASK_HUB`.
- Commit locally. Do not push.
