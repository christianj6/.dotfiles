# Rule: a "fixed" claim must name its call sites

Naming a pattern that cost this project three separate defects in one day (2026-11-03). Every one had the same shape: **a function was verified, the system was inferred.**

## The pattern

Someone (often me) reads a function, confirms it behaves correctly, and reports "X is fixed". The function *is* correct. A **caller** bypasses it, or a **second copy of the same rule** disagrees with it. The claim was true about a function and false about the system.

Three instances, all today:

| Claim | What was actually verified | What bypassed it |
|---|---|---|
| "a claimed hand-over is always an Effect" (`3c483b0`) | `claims_have_effects` rebuilds the route's Effect | a **speculation hit** reused a decision built before the final transcript — and `delegate_to`, which never calls `handler_for` |
| "the duplicate factory is fixed" | the new `holds` guard makes the in-decision branch inert | the **old binary** was still running; only the restart closed it |
| "explicit fix-it goes coordinator-first" (`99c165a`) | the precedence **inside** `handler_for` | `delegate_to:3217` calls `dev_agent()` and never `dev_id()`, so implied tasks about bro still reached bro's Claude |

Each fix was real. Each report was narrower than the truth.

## The rule

**Before saying "X is fixed", enumerate what X covers:**

1. **Name the call sites.** Not "`handler_for` prefers the coordinator" but "`handler_for` prefers the coordinator, and the sites that select a destination for bro's own work are `_command:2904` and `delegate_to:3217`, both now routed through `own_work_dest`."
2. **Grep for the rule, not just the function.** If a precedence or mapping exists in one place by design, prove there is no second copy: search for the literals the rule keys on, not only for its name.
3. **Check the thing that runs.** A test proves the code path; the microphone, the binary, the served page, the running process prove the integration. Two of today's three defects survived because tests passed while the running system did something else.
4. **Write the test at the shape that was broken.** A status-ask test passes while gap 3 lives. The proving test must be the *implied task about bro*, because that is the caller that bypassed the resolver. A test written the obvious way re-hides the bug.
5. **State the residual.** "Verified for the explicit path; `delegate_to` is not yet routed" is a useful report. "Fixed" was not.

## Why it keeps happening

Fixing is local and satisfying; boundary-finding is diffuse and feels like re-doing the work. And a function-level claim reads as complete because it is *precise* — precision creates confidence that coverage doesn't earn. The tell is a claim with no call sites in it.

## Fourth instance (same day): absence of a name is not evidence about a behaviour

Reporting on `delegate_to`, I checked that `dev_id()` did **not** appear at the call site and concluded bro's coordinator was bypassed. Wrong: the function present was `dev_agent()`, and `is_dev()` accepts `agent == "omp"` in bro's repo — it *is* the coordinator's pane. I inferred from a **name** and never read the **predicate**.

Grep for absence is a weak test. Before claiming "X is bypassed", read what the thing that *is* called actually returns:

- "`dev_id()` is not called here" → not a finding.
- "`dev_agent()` returns `omp-v34-wdp5`, which is `dev_id()`" → the finding, and it refutes the claim.

The stronger form of the check is a **value**, not a name: print what the call returns on the real data.

## The one-line version

> Any "X is fixed" claim has to name the call sites it covers, or it is a claim about a function, not a system.

## Corollary for the reverse direction

The same discipline catches false alarms: the "two tasks silently dropped" incident was me inferring intent from a `by=owner` stamp and a ~45 s gap without checking the one witness who could know (the owner had clicked them). Evidence about a *mechanism* is not evidence about an *event*. Name what you observed and what you inferred, separately.
