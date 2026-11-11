# TASK: work mode on by default

Owner, 2026-11-09: **"work mode on by default"**.

## Why

His thor agent (`omp-v36-wgp1`, live in herdr) was absent from prescient's agent list.
Cause: `data/settings.json` had `work_mode: false`, and `prescient/gantt/bro_stack.py:47-48`
filters anything under `/tallence/` (and projects `thor`/`telia`) while work mode is off.
The filter worked as designed; the owner's expectation is different — he wants the work
agents visible.

**CORRECTION (from prescient's coordinator, and I verified it): that `false` was very
likely TEST RESIDUE, not the owner's choice.** The file's mtime is `Nov 11 08:07`,
matching their G1 probes, and an earlier probe round (A2) recorded that it POSTed
`{"work_mode": false}` to `/api/settings` on port 8917 — which **shares `data/` with
8765**, so it wrote the owner's real file. That report also says plainly: *"I can't tell
what it was before."* Nothing in this repo records the owner ever setting it false.

So **do not report "the owner had work mode off"** — that would be a false history, and
the honest statement is "a test probe wrote the file; the owner then stated the default he
wants". The task is unchanged.

## What to change (prescient)

`prescient/gantt/settings.py`:

```python
def read_settings() -> dict:
    ...
    return {"work_mode": bool(data.get("work_mode")) if isinstance(data, dict) else False}
```

1. **Flip the default to `True`** when the key is absent or the file is unreadable — i.e.
   `data.get("work_mode", True)`. A missing settings file must mean "work mode on", not
   off, or a fresh machine silently hides his agents again.
2. **Update the module docstring** — it currently says *"work_mode: off (the default) keeps
   work repos … out"*. The docstring is the next reader's source of truth and would
   otherwise contradict the code, which is the exact failure mode this project keeps
   hitting (a permissive/silent default beside a rule).
3. **Set the current `data/settings.json` to `{"work_mode": true}`** so it takes effect now
   without waiting for a missing-file scenario. That file is gitignored owner data —
   changing it is part of this task, not a side effect.
4. Keep `set_settings` validation as-is (still a bool).

## Acceptance

1. With `data/settings.json` deleted, `settings.work_mode()` returns **True**.
2. With `data/settings.json` = `{"work_mode": false}`, it returns **False** — an explicit
   off is still honoured.
3. With `{"work_mode": true}`, True.
4. After the change, `GET /api/agent-board` **includes** `omp-v36-wgp1` / `thor-voiceai`
   under its proper project name. Show the row.
5. The docstring no longer says off is the default.
6. Existing prescient tests pass; add the three settings cases above if not covered.

## Implication to state, not to solve

Turning work mode on means work projects become visible to bro's stack and to the hub —
that is the point, and the owner asked for it. Two things follow, both worth one line in
the report, neither blocking:
- auto-task may now open hub items for work-project panes;
- bro may answer about work projects by name.

If either creates real noise, that is a separate decision. Local only: `settings.json` is
gitignored, and hub items live in prescient's local SQLite, so nothing here reaches the
public dotfiles repo.

## Separately noted, not part of this task

**marketing (`omp-v36-wgp3`) is absent from `herdr agent list` entirely** — a dead pane,
not a filter. Worth a look on its own; do not bundle it here.
