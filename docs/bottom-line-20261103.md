# Bottom line, 2026-11-03

## Rollout: complete

Every agent pane on **v35**. Zero stale.

| Tab | Pane | Version |
|---|---|---|
| dotfiles | `wD:p9` omp, `wD:pA` claude | v35 / v~35 |
| prescient | `wD:p7`, `wD:pC` | v35 / v~35 |
| bro | `wD:p5`, `wD:p6` | v35 / v~35 |
| thor | `wG:p1` | v35 |
| marketing | `wG:p3` | v35 |
| heinzel | `w5:p1D`, `w5:p1A` | v35 / v~35 |

Every restart **resumed** its session. Thor needed no action (already v35); heinzel's
Claude was rolled last, once it went idle, so its work was never interrupted.

Services after all of it: prescient `200`, bro tray `200`, hub mode `prescient`.
All three repos pushed and in sync.

## FIXED

| What was broken | Evidence it is fixed |
|---|---|
| **A nudge into an nvim-nested omp pane needed a human Enter** | `deliver_verdict` → `nudged: ok, "transcript shows it"` on two panes. `REPL_TOP` matched only a standalone REPL, found a stale top, saw no text, and reported "box looks submitted". |
| **Projects went amber→grey instead of green** | `ready` invariant holds on all six projects. Two independent bugs: prescient ranked one role's items only; the plugin's auto-ready was agent-keyed while items carry `agent: null`. |
| **`--explain` contradicted the icon** | Its "bro tasks" line used the old agent-keyed selector beside a project-keyed icon, printing "none open" next to green. |
| **A parked item vetoed green permanently** | One unmarkable item beside working work made two candidates = "ambiguous" = never green. Candidates narrowed to states the harness can drive. |
| **The privacy guard missed push-time** | `--no-verify` + push published unchecked (reproduced, then fixed). A secret committed and later deleted is now caught — the guard reads every commit in the push. |
| **An anonymous task write was recorded as the owner** | Refused, with `by` required; verified no event written. |
| **A question became a work item; a claimed hand-over had no effect behind it** | Question-about-feature answered from capability, zero hub creates; `route` without an `Effect` is rebuilt at commit with a `route_without_effect` event. |
| **The duplicate factory (4 rows from one utterance)** | `Held.holds` keeps the hub branch out of the decision; a regression test pins 4-without / 1-with. |
| **Listening mode showed as "on" while bro held your thoughts** | Tray reads light-blue "listening"; an unknown tier reads "unknown", never healthy. |
| **Stale doorbell lines never cleared** | Swept when herdr has no such agent; every prune logged and archived; a pane-id bell now actually delivers. |

Suites: prescient **953**, bro **768**, plugin **68**, go build clean.

## STILL NEEDS FIXING

1. **Auto-ready's own write is unproven live.** Correct in isolation (queued + idle settler + finished answer → MARK), and correctly blocked in practice — but never watched end to end, because every active project either marks its own work or is mid-flight. Not a suspicion; simply not yet observed.
2. **`which_kind` files "tell heinzel to check the status of the sync" as `status`, not `task`.** Telemetry-only: the only caller is the "which project?" slot, which a status ask with a named recipient never reaches. I tried the other reading, the test documents this one, and I reverted — it is the safer default and the distinction cannot change a route.
3. **Honesty lint false positives** (`docs/honesty-false-positives.md`): "Two are ready for you to try" flags `ready`; "nothing was sent" flags `deliver` — a *denial* read as a claim. Each costs one retry, not a wrong reply. Deliberately deferred: widening `_NEG` can silently mask a true claim.
4. **Bare-No debt** and **two behaviour bugs** on bro's queue; the self-improvement bench is frozen at 78×3 and **uncalibrated** — it lists failures but cannot judge improvement.
5. **Wave 5**: bro's local task storage still present behind `TASK_HUB=local`. Archive written and gitignored.
6. **Trello replication** is still a stub; the event outbox exists.
7. **Five real hub rows** need the owner: `tk-fcf2134447ac` (a question the dev agent answered) and the four duplicate idea rows. Only the owner may drop.

## The one thing I would do next

Calibration of the bench — it is the only thing that turns "this change looks better" into "this change is better", and every behaviour fix today landed on argument rather than measurement.
