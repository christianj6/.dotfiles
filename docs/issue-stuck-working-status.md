# Bug: heinzel's omp pane pinned at "working" — the registry entry is wedged

Owner: *"the heinzel omp pane agent status seems bugged. it is stuck in working state even
though its not doing anything."* Reproduced and diagnosed; the pane is genuinely idle and the
**report path is inert**.

## The pane is idle, by every measure except the sidebar

| what | says |
|---|---|
| transcript | `answered`, **41 minutes** ago |
| last turn | 2 calls, ended 41 min ago; prompt was a prescient task nudge |
| `herdr agent explain omp-v36-w5p1d` | **`state: idle`**, `rule: none` |
| `herdr agent list` (what the sidebar renders) | **`working`** |
| process tree | healthy: `zsh 14308 → nvim 23877 → nvim --embed 23878 → omp 24000` |

So omp is alive, the tree is fine, the engine's own explain says idle — and the registry
disagrees.

## Reports do not apply, in any form

```
herdr pane report-agent --source custom:coordinator-probe --agent omp --state idle  w5:p1D  -> accepted, status stays working
herdr pane report-agent --source custom:fresh-<random>  --agent omp --state idle  w5:p1D  -> accepted, status stays working
herdr pane report-agent --source custom:omp-watch       --agent omp --state idle  w5:p1D  -> accepted, status stays working
herdr pane report-agent --source custom:omp-watch       --agent omp --state blocked w5:p1D -> accepted, status stays working
```

Every call returns success and **nothing applies** — not `idle`, not `blocked`, not from a
fresh never-used source name. That is the failure `watch.py` documents at lines 102-113:

> *"reports from OUR source can silently stop applying — exit 0, no error body, registry state
> frozen — while the SAME source keeps working for other panes, and a ONE-OFF report from a
> never-before-used source name lands instantly"*

**Except the documented remedy (rotate to a fresh source) does not work here**, which makes this
a case the existing recovery does not cover. Reported state is frozen for this pane, full stop.

## Why the idle heuristic did not save it

The heuristic is sound and would have: `tail_verdict = answered`, `quiet = 2474 s`,
`limit = IDLE_GRACE_SECONDS`, so it computes **idle** (`quiet > limit`). The logic is right;
its *report* is what is being dropped. The heuristic can only report — it cannot force.

## The fix

**Recovery (immediate): restart that pane's omp.** `workspace-rollout` will not do it —
`--only w5:p1D` reports `up-to-date` because the version is already v36, and the wedge is not a
version problem. The restart has to go through the yarepl RPC path the rollout uses: `/exit` via
`nvim` chansend, then `yarepl_start` to resume.

**Prevention (the real fix), two parts:**

1. **When rotation fails, escalate.** `ROTATE_AFTER_SENDS` / `MAX_ROTATIONS_WITHOUT_CONVERGENCE`
   already bound the retries, but when the bound is exhausted the pane is left silently wrong.
   After the last rotation fails, the watcher must **say so once** — a `report_wedged` event
   naming the pane — so this is visible in a log rather than only in the sidebar.
2. **A last-resort re-registration.** If a report has not converged after N rotations *and* the
   pane's own `herdr agent explain` disagrees with the registry, the watcher can release and
   re-report the agent for that pane (`pane release-agent`, then a fresh `report-agent`). That is
   a heavier hammer than rotating the source name, and it is the one that should be tried last —
   but it is the only thing left when every report is dropped.

## Acceptance

1. Restarting `w5:p1D`'s omp clears the stuck state; `herdr agent list` then matches
   `herdr agent explain` (`idle`).
2. The watcher emits a one-time `report_wedged` event (or equivalent log line) when rotation is
   exhausted and the registry still disagrees with itself.
3. A test for the wedge: a fake registry that accepts a report and does not apply it must cause
   the escalation path, not silence.
4. `w5:p1A` (claude, genuinely working — transcript written a minute ago, rule
   `osc_title_working`) is untouched.
5. No change to the idle heuristic — it computed the right answer.

---

## ROOT CAUSE: a foreign `herdr:claude` claim on an omp pane (recovered)

The worker's prevention commit caught it, and the event named the cause:

```
report_wedged w5:p1D {registry: working, verdict: idle, explain: idle,
                      foreign_claim: herdr:claude, ...}
```

**`foreign_claim: herdr:claude` on a pane whose occupant is `omp`.** That is the documented
mechanism in `scripts/herdr-clear-agent-claims.sh` (written 2026-09-15, same symptom):

> *"Any `claude` process that inherits a pane's `HERDR_PANE_ID` registers one — including a
> one-shot `claude -p` probe run from that pane's shell, even if the pane's real occupant is omp.
> After that, herdr accepts omp-watch's report-agent calls with a clean "ok" and never applies
> them: the pane's sidebar status freezes at whatever state was live when the claim landed."*

That explains every measurement: `herdr agent explain` said `idle` (the engine knew), the
registry said `working` (frozen at claim time), and **four different `report-agent` calls —
idle, blocked, own source, fresh source — were all accepted and applied none**.

`claude -p` probes run from that pane today are the likely source: I have been running
`/Users/christianjohnson/.herdr-discord-venv/bin/python` and `claude`-family commands from panes
all session.

## Recovery

The script's own advice for one pane is *"close and recreate just that pane (a new pane id
carries no claim)"* — much lighter than its alternative, which stops the server and kills every
pane process.

```
herdr pane close w5:p1D
herdr pane split --pane w5:p1A --direction right --cwd <heinzel> --env HERDR_NO_NVIM=1   -> w5:p1T
herdr pane run w5:p1T nvim ; ctrl+a                                                       -> nvim + omp
```

**Verified after:**

```
w5:p1A | claude -> working      (untouched, genuinely working)
w5:p1T | omp    -> idle         (reports correctly, unlike the pinned pane)
claim on omp-v36-w5p1t: none    (vs the old pane's herdr:claude)
```

The new pane id carries no claim, so the report path works again — which is the proof that the
claim was the cause and not the idle heuristic.

## What still needs fixing, in the harness

1. **Do not let an `omp` pane accept a `herdr:claude` claim.** That is the actual defect: the
   claim is registered by whatever process inherits the pane's `HERDR_PANE_ID`, with no check
   that it matches the pane's real agent kind.
2. **`herdr-clear-agent-claims.sh` exists and nobody ran it** — because nothing surfaced that the
   state was wrong. `report_wedged` now does (the worker's prevention commit), which is the
   durable half.
3. **Avoid `claude -p` probes from an omp pane's shell** — they are the likely origin. If a probe
   is needed, run it with a clean environment (`env -u HERDR_PANE_ID`).
