# Q1 correction: `plan` and `tweak` must NOT become hub work items

**My earlier ruling was wrong.** `docs/spec-task-hub-answers.md` said: plan/tweak → `(prescient, dev)` hub items, on the reasoning that "untracked delivery is the failure mode we're removing". That reasoning was sound about *visibility* but wrong about *identity*: a planning capture and a work item are different kinds of thing, and collapsing them destroys the capture inbox.

## The evidence (live, 2026-11-03)

- `bro/taskhub.py:155` lists `queue` in `HUB_ROLES`; `hub_target()` (line 164) maps every `queue` destination to `(prescient, dev)`.
- Consequence: **"Good biodeed milk in my planning inbox"** (`tk-0c432af1f87b`) is a `prescient/dev` task in state `ready`, when it should be an item in `data/inbox.json`.
- `data/inbox.json` no longer receives plan hand-overs at all. Tweaks likewise become dev tasks instead of `tweak.json` entries.
- Found by prescient's coordinator while triaging a misrouted item; it is bro's code, and it was reported there with this root cause.

## The rule (replacing Q1)

| Destination role | Where it goes |
|---|---|
| `queue` (`plan`, `tweak`) | **the pre-flip path**: `data/inbox.json` for a plan capture, the tweak store for a tweak. NOT a hub item. |
| `coordinator` / `dev` | a hub work item, `project` from the agent's repo, `target` the role. |

Rationale: the hub tracks **work for an agent**. A plan capture is the owner's own note — it has no owner-agent, no verdict, and no lifecycle beyond "sorted later". Giving it a work-item state machine is why an errand showed up as `ready` work for prescient's Claude.

## Implementation (bro)

- `hub_target()` must **refuse** role `queue` (`raise ProjectUnknown`/`ValueError`), and `on_hub()` must return False for it, so the caller falls through to the pre-flip delivery path unchanged.
- Do not delete the queue→inbox code path: it is the correct path and it still exists.
- Verification must check **both** destinations: a plan hand-over lands in `inbox.json` and creates **no** hub item; a coordinator hand-over creates a hub item and touches no inbox.

## Cleanup owed

`tk-0c432af1f87b` ("Good biodeed milk in my planning inbox") is a misrouted capture sitting in the hub as `prescient/dev ready`. It should be moved back to the inbox as a capture and the hub row removed — after the fix, so it cannot re-route.
