# Owner decision: explicit "fix it" goes to the coordinator first

**Decided 2026-11-03 by the owner, verbatim: "explicit fix it still to coordinator first."** This settles the question I raised and left open. Recording it here so it is never re-litigated from inference.

## The rule

Explicit dev work — "fix it", "fix the heinzel sync", "add a retry to the heinzel sync" — is handed to the **project's coordinator**, which owns deciding whether it or its Claude does the work. Its Claude is the fallback only when no coordinator runs. This is the same precedence as `99c165a` and `tk-a49ea85f1d54` (the owner's 16:07 correction), now applied to the explicit path too.

For **bro's own** work, "coordinator first" means bro's coordinator (`dev_id()`, the omp pane), not bro's Claude.

## What already complies (verified, not assumed)

`voicebridge.py:2904`:

```python
if dev_request(text):
    project = self.named_project(text)
    dest = self.handler_for(project, stack) if project else (
        agent_destination(a) if (a := self.dev_agent_for(text)) is not None else None)
```

When the owner **names a project**, this already calls `handler_for`, which now prefers `coordinator:<project>` when available and falls back to that project's Claude. So a project-named explicit fix already complies.

## The two gaps that remain

### 1. No project named → bro's own Claude, skipping bro's coordinator

`dev_agent_for(text)` with no project named returns `dev_agent(agents)` — **bro's Claude**. Per the decision it must be bro's **coordinator** (`dev_id()`), with its Claude as fallback.

Verified:
```
'fix it and restart'   dev_request=True   -> dev_agent_for -> bro's Claude (skips dev_id())
```

Fix at `:2904-2906`: when `dev_request(text)` and no project is named, try `dev_id()` first (respecting availability), then `dev_agent_for` as the fallback. Do **not** make `dev_agent_for` itself return the coordinator — it is called from several places (honesty's offer at `:2437`, the noted path, the icon path) where "the Claude who can do this" is the right question; the change belongs at the explicit-work site.

### 2. `coordinator:bro` does not exist, so `handler_for('bro', …)` cannot reach bro's coordinator

The live stack's destinations:
```
plan, tweak, coordinator:dotfiles, coordinator:prescient, coordinator:thor-voiceai, coordinator:heinzel, top
```
There is **no** `coordinator:bro` — bro's own coordinator is exposed only as `agent:<omp pane>`. So if anything ever calls `handler_for('bro', stack)` it will skip the coordinator branch and return bro's Claude, silently contradicting this decision.

Fix: either add `coordinator:bro` to the stack (in prescient's `bro_stack.py`, mapping to bro's omp pane), or make the explicit-work site special-case bro's own project via `dev_id()`. **Prefer the former** — one vocabulary, `handler_for` stays the single resolver — but it is a cross-repo change (prescient) and should be routed there rather than done in bro.

## Acceptance

1. `"fix it and restart"` (no project) → the effect's dest is bro's **coordinator**, not bro's Claude.
2. `"fix the heinzel sync"` → `coordinator:heinzel` when it runs; heinzel's Claude when the coordinator is down.
3. `"fix it"` with bro's coordinator **down** → falls back to bro's Claude, and says who it went to.
4. Coordinator down **and** Claude down → the existing honest refusal ("isn't running, so I can't pass that on"), unchanged.
5. A non-explicit remark ("that's annoying") still goes nowhere — this must not turn every utterance into a hand-over.
6. Existing `tests/test_coordinator_first.py` cases still pass.

## Note on scope

This is **not** the which-slot work and should not be bundled with it. That spec is about *what kind of ask* a request is; this is about *who receives* explicit work once it is known to be work. Two different questions, two different diffs.

## Still open, deliberately

The mic observation after `3c483b0` — "yes" to an offer → exactly one `task_hub_effect` — is **deferred by the owner ("we can ignore the mic observation for now")**. It stays recorded as unproven rather than being quietly dropped.

---

## Acceptance #5, pinned with a baseline (measured before the build)

The coordinator is right that this is the failure mode to guard: **"coordinator first" must not become "everything is work".** I measured the current behaviour so the build has something to regress against, rather than a sentence to interpret.

Complaints and filler — none may produce a hand-over:

| utterance | `dev_request` | `implied_task` | `explicit_filing` | `which_kind` |
|---|---|---|---|---|
| "that's annoying" | False | False | False | `None` |
| "that is so annoying" | False | False | False | — |
| "this is useless" | False | False | False | `None` |
| "that's a shame" | False | False | False | `None` |
| "hmm" / "okay" / "nice" / "wow" | False | False | False | `None` |

**The harder case, and the one that would actually bite** — a complaint that *names a project*, because that is the shape where "coordinator first" could leak into "everything is work":

| utterance | `which_kind` |
|---|---|
| "dotfiles is annoying" | `None` |
| "the heinzel sync is useless" | `None` |
| "bro's buffer is terrible" | `None` |
| "heinzel is slow today" | `None` |

All four already classify as `None`. **Keep them that way.** The rule for the build: a project name plus a complaint is still a complaint — `named_project` finding something must never be sufficient to construct an Effect. If any of these starts returning `task`, the change is wrong regardless of how well it works for "fix it".

Explicit work, for contrast, must keep firing: `"fix it"` and `"fix it and restart"` → `dev_request=True`, `implied_task=True`.
