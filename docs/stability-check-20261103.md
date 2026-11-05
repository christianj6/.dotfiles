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

## What is NOT verified

1. **The live auto-ready write path.** I watched it *refuse* for real reasons ("herdr says working, not settled") and saw the candidate visible where it was previously invisible. I have not yet watched a live item go `queued → ready` end to end, because the settler has been busy the whole time. That needs one quiet minute with an idle omp.
2. **prescient's `multiple`-item ranking under a mixed set.** I confirmed the invariant on today's data; I have not constructed a project holding both a `ready` and a `working` item and checked which one the icon names.

## Unpushed

- bro: **58 commits** (33 code, 25 docs).
- dotfiles: everything of mine is pushed.

## Verdict

Ready to roll panes **except** for the one unverified path above. Rolling restarts agent processes — and if the live `queued → ready` transition has a bug, restarting first means discovering it in a fresh session with no baseline. I would rather watch one item go green quietly first, which costs a minute.
