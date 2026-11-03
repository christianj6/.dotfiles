# Status: .dotfiles
Updated: 2026-11-03 16:00 (Europe/Berlin)

## Now
- Voice hand-off is live end to end and the owner has used it on the real mic. Listening mode is up and proven.
- One known defect in flight: a spec-hit turn can claim a hand-over with no effect behind it (bro's coordinator has the spec).

## Next
- bro: the claim-without-effect invariant (see Waiting on).
- Wave 5 finish: remove bro's local task storage (archive written and gitignored).
- Watch the first real week of hub usage; the auto-task rule is live but young.

## Waiting on the owner
- **bro has 9 commits unpushed** on main. Nothing is at risk locally, but they are only on this machine.
- `tk-fcf2134447ac` (bro/dev, ready): a *question* that became a work item. The dev agent answered it in the summary, so it is complete in substance — drop or answer it as you see fit. Not touched by me.

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
- **Three hub bugs found by smoke-testing**, not by assuming: a dropped hub dispatch in the plugin's auto-task path, env-only switches invisible to the herdr-launched daemon, and a self-referential auto-task loop.
- **Auto-task re-enabled** with a rule: coordinators are never auto-tasked; pattern matching is only a second guard.

## Waiting on — the open defect (bro)

A turn can say "I'll get that to the bro agent." with nothing released. Root cause traced: a **speculation hit** reuses a Decision built before the final transcript, and only `effects` is acted on — so a `route` action is decorative. The same shape appeared three times today (a misfiled task, this claimed delivery, an earlier "already routed"). The fix is an invariant at the commit, not more phrase matching:

1. A reply claiming a hand-over must have a released effect or a pending receipt — build the effect from the action's destination, and log `route_without_effect` loudly when it fires.
2. Re-run release-shaping before committing a spec hit (a hit shortcuts the model call, never the post-processing).
3. Bare-yes consent: `'Yes'` matches none of `implied_task`/`TELL_TO`/`SEND_IT`/`HAND_TO`, so consenting to bro's own offer could never become an Effect. Use `self.asked + YES_START`, which `wanted()` already does.
4. Then, third priority, the `honesty.DELIVER` phrase family.

Spec: `docs/spec-claim-without-effect-mechanism.md`.
