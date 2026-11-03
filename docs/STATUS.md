# Status: .dotfiles
Updated: 2026-11-03 17:35 (Europe/Berlin)

## Now
- Voice hand-off works on the real mic; listening mode is live and proven (held thoughts, one closing turn, zero effects).
- The claim-without-effect class is fixed and pinned by a regression test. The mic observation ("yes" to an offer →
  exactly ONE `task_hub_effect`) is **deferred by the owner** and stays recorded as unproven, not dropped.
- The which-slot intent fix (a status question must not become a work item) is spec'd with the build in flight.
- Explicit "fix it" → coordinator first: two gaps remain (no-project falls to bro's Claude; `coordinator:bro` doesn't
  exist). Spec'd and routed to both repos.

## Next
- Wave 5 finish: remove bro's local task storage (archive written and gitignored).
- Watch the first real week of hub usage; the auto-task rule is live but young.

## Waiting on the owner
- **Nothing blocking your decisions.** Explicit "fix it" is decided: coordinator first (`docs/spec-explicit-fix-it-coordinator-first.md`). The mic observation is deferred by your call and stays recorded as unproven.
- `tk-fcf2134447ac`, `tk-b8fdc5c99e33` + three duplicates (`tk-1c332dde48ea`, `tk-5809a064b04e`, `tk-2840f7a41414`):
  real rows that need a drop or an answer. Only you may drop, and I will not record a `harness` drop to tidy up.

## Blocked
- Nothing.

## Recently landed
- **Task hub is live.** prescient owns tasks (SQLite store + enforced state machine + HTTP + CLI); bro is a client behind `TASK_HUB=prescient`; Trello is the async audit log. bro's old store is frozen and archived.
- **One route, one delivery path, one resolver.** Coordinator inbox = `state=queued&target=coordinator`; nudges go through prescient's hardened `_deliver`; the plugin's icon diagnostics read prescient's `{status, why}` (ranks v2, version-gated).
- **All panes on v34**, sessions resumed; agents instructed to use `prescient task start|ready` (bro's verbs forward for one release).
- **The voice hand-off works on the real mic.** `tk-8076367bafcd` went queued → working → ready through bro's own voice and the dev agent's own start/ready; `tk-735885816f18` correctly filed to heinzel after the project-from-repo fix.
- **A capture is not a work item.** My Q1 ruling was wrong and was reversed: plan/tweak (role `queue`) go to the inbox, never the hub. Verified live both ways — `deliver('plan')` returns an `ib-` capture with zero hub rows; a coordinator hand-off creates a hub row with the inbox untouched.
- **Hub tasks' buttons reach a live agent.** `_live_agent` resolves per click (stored name → project's agent for the role), so try/press/reopen work on `agent: null` rows — and reopen raises *before* the write, so a "not quite" comment can no longer vanish silently.
- **Listening mode is live.** Enter by voice, thoughts are held unanswered, one closing phrase hands the whole stretch over as one turn, 10 quiet minutes ends it. Verified on the owner's own mic: three thoughts held (1/2/3), 23.0 s in LISTENING, one 11-word turn, **zero effects**. The life view shows it in light blue — never grey, never "on".
- **Unattributed task writes are refused** (both docks). Not an incident — the owner's own clicks — but a default that said "the owner" would have made a future anonymous write indistinguishable from a real one in the audit log.
- **Stale doorbell lines are swept** (only when herdr has no such agent; every prune logged and archived, unknown ≠ dead), and a bell addressed by pane id now actually delivers.
- **The claim-without-effect class is closed** (`3c483b0` + `4a056ff`): a `route` action alone released nothing, so bro could say "I'll get that to the bro agent" with no effect. Now `Held.holds = True` keeps the hub branch out of the decision, `claims_have_effects` rebuilds the Effect from the action's destination at both decide and commit (spec hits included), consent to an offer becomes that offer's Effect, and `bro/hubguard.py` trips on the three pre-fix runs. The duplicate factory behind it (four identical rows from one utterance) is explained: the in-decision branch ran once per used speculative prefix.
- **The privacy guardrail is closed** (`b62443f`). Audited by reproducing the hole I found, then verifying the fix: a
  `--no-verify` commit followed by a push now fails the push (exit 1) naming the offending **commit**; a clean push
  still succeeds (exit 0). `.githooks/pre-push` runs `check-private.py --pre-push`, which audits **every commit the push
  publishes** — a secret committed and then deleted is still caught. `scripts/git-guard.py` shares one guard between omp
  and claude, and nothing is skipped silently any more (a file too large to scan warns instead of vanishing).
- **Three hub bugs found by smoke-testing**, not by assuming: a dropped hub dispatch in the plugin's auto-task path, env-only switches invisible to the herdr-launched daemon, and a self-referential auto-task loop.
- **Auto-task re-enabled** with a rule: coordinators are never auto-tasked; pattern matching is only a second guard.

## Waiting on — the open defect (bro)

A turn can say "I'll get that to the bro agent." with nothing released. Root cause traced: a **speculation hit** reuses a Decision built before the final transcript, and only `effects` is acted on — so a `route` action is decorative. The same shape appeared three times today (a misfiled task, this claimed delivery, an earlier "already routed"). The fix is an invariant at the commit, not more phrase matching:

1. A reply claiming a hand-over must have a released effect or a pending receipt — build the effect from the action's destination, and log `route_without_effect` loudly when it fires.
2. Re-run release-shaping before committing a spec hit (a hit shortcuts the model call, never the post-processing).
3. Bare-yes consent: `'Yes'` matches none of `implied_task`/`TELL_TO`/`SEND_IT`/`HAND_TO`, so consenting to bro's own offer could never become an Effect. Use `self.asked + YES_START`, which `wanted()` already does.
4. Then, third priority, the `honesty.DELIVER` phrase family.

Spec: `docs/spec-claim-without-effect-mechanism.md`.
