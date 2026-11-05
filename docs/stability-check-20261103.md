# Stability check before rolling panes (2026-11-03)

The owner asked: keep going until stable, then say when panes can roll.

## Suites — all green

| Repo | Result |
|---|---|
| prescient | **953 passed** |
| bro (python) | **768 passed** |
| bro (go) | `go build ./...` exit 0 |
| lifeview plugin | **68 tests OK** |
| plugin smoke (`--explain`) | exit 0 |

## The delivery bug — FIXED and proven end to end

This was the blocker: every nudge into an nvim-nested omp pane needed a human Enter.

- `_box()` now resolves the last titled top **that has a bottom border before any other top**, else `None`; borders accept nvim's prefix; `_waiting` returns `None` (not `False`) when no box is on screen.
- Verified on the failing layout (`wD:p9`): in-box → `True`, absent → `False`, no box → `None`.
- **Live proof:** `deliver_verdict('omp-v34-wdp5', …)` → `{'nudged': 'ok', 'retryable': False, "… transcript shows it"}`, and the text appears in that pane's transcript. No human keypress.

## The icon invariant — holds on every project

| project | status | ready items | agrees |
|---|---|---|---|
| bro | working | 0 | OK |
| prescient | idle | 0 | OK |
| heinzel | working | 0 | OK |
| dotfiles | ready | 2 | OK |
| thor-voiceai | working | 0 | OK |

`any item ready ⇒ project ready` is true across all five. That is the owner's original complaint, closed.

## Surfaces

| Surface | Result |
|---|---|
| bro tray `/api/tasks` | HTTP 200, 142 items |
| bro `/api/task-hub` | `{"mode": "prescient", "source": "env"}` |
| prescient page `/` | HTTP 200 |
| prescient `/api/voice` forward | responds through to bro |
| destinations | 9, including `coordinator:marketing` (a new project the owner started) |

## Fixes I made while reviewing the worker's diff

1. **`--explain` contradicted the icon** — it used the old agent-keyed selector for its "bro tasks" line while the icon used the project selector, so it printed "none open" beside a green icon. The diagnostic is what you use *because* you don't trust the icon; it must not disagree with it.
2. **An unmarkable item vetoed green permanently** — `ready_candidate` was "open and not ready", so `created`/`parked`/`undelivered` counted as candidates even though the harness has no route from them to `ready`. One such item beside working work made two candidates = "ambiguous" = never green. Narrowed to states the harness can actually drive. Two genuinely markable items still count as ambiguous, and the new test asserts both halves.

Both were found by driving the real code, not reading the diff.

## The live transition — watched, with its caveat

On `marketing` (idle omp, zero items, nothing in flight):

```
15:16:16  created -> queued   by owner
15:16:23  queued  -> working  by agent
15:16:24  working -> ready    by agent
/api/tasks/status?project=marketing -> omp-v35-wgp3 | ready | "a task is ready for your verdict"
```

**queued → ready in 8 seconds, and the icon went green.** But the events say `by=agent`, and the harness writes `by=lifeview-harness` — so this was the **coordinator marking its own work ready**, not auto-ready. I am not counting it as proof of the harness path.

**What that taught me:** the coordinator does this well on its own, which is exactly why the asymmetry was invisible on prescient and visible elsewhere. On a project whose agent marks its own work, auto-ready is a backup, not the mechanism.

**Auto-ready itself, verified in isolation:** with one `queued` item, an idle settler and a finished answer, `ready_check` returns `MARK`. So the code path works. In the live workspace it is currently blocked on `bro` by `started-by-the-agent` — a correct guard, not a bug.

**Still not watched live:** the harness's own write. It needs a project whose agent does *not* mark its own work, with an idle settler — and on this board every active project either self-marks or is mid-flight. I will not manufacture that by disabling a safety guard.

## What is still not verified

prescient's ranking under a **mixed** set: a project holding both a `ready` and a `working` item, to check which one the icon names. The invariant held on today's data across all five projects; the mixed case is untested.

## Unpushed

- bro: **58 commits** (33 code, 25 docs).
- dotfiles: everything of mine is pushed.

## Verdict

Ready to roll panes **except** for the one unverified path above. Rolling restarts agent processes — and if the live `queued → ready` transition has a bug, restarting first means discovering it in a fresh session with no baseline. I would rather watch one item go green quietly first, which costs a minute.
