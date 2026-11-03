# "I'll get that to the bro agent." — a claim with no effect, and the precise mechanism

spec from `docs/voice-overhaul/specs/2026-11-03-claim-without-effect.md`. I traced it further than the first report: the bare-yes gap is real, **but it is not what happened here.**

## The two turns

| Turn | Owner | bro | actions | effects |
|---|---|---|---|---|
| 9 | "No um give it to you and then it might need to be routed depending on what it needs to touch" | "Want me to take a look at that?" | `[{destination: top, tool: propose}]` | `null` |
| 10 | **"Yes"** | **"I'll get that to the bro agent."** | `[{destination: top, tool: route}]` | **`null`** |

Turn 10's meta: `decide_ms: 49`, `layer: "speculation"`, `spec: "hit"`.

## Mechanism — corrected

**The reply was pre-synthesized speculation, committed as a hit.** `voicebridge.py:3272-3279`:

```python
for d in list(self.spec.get(utt, [])):
    if norm(d.text) == norm(final):
        ...
        hit = cur
...
d = hit or self.decide(final, mid, spec=False)
```

On a spec hit the Decision is **reused wholesale** — its `actions`, its `reply`, and its `effects` — as computed while the owner was still speaking. So:

1. The speculatively-built decision produced a `route` action for `top` and the reply "I'll get that to the bro agent."
2. It carried **`effects: []`**.
3. `effects` is the only thing the commit acts on: `fx.held(...)` builds from `effects`, hub creation happens per effect, `tasks.opened` runs per effect (`voicebridge.py:3336-3348`).
4. With no effect, the release loop has nothing to run → **no `task_hub_effect`** → the reply is spoken as fact anyway.

**So a route action is decorative.** It records intent for the chat; it routes nothing. That is the invariant worth enforcing, and it is broader than "the bare-yes path": any speculation hit that produces a route/propose action with no effect inherits the same lie.

**The bare-yes gap is a second, contributing bug** — at `voicebridge.py:2748`:

```python
if (not d.effects and (implied_task(said) or ((TELL_TO.search(said) or SEND_IT.search(said) or HAND_TO.search(said))
                                              and self.named_project(said)))
```

Verified on the real functions:
```
'Yes'        implied_task=False tell_to=False send=False hand=False
'yes please' implied_task=False tell_to=False send=False hand=False
'go ahead'   implied_task=False tell_to=False send=False hand=False
```
The owner's consent utterance is literally "Yes", so **the delegation block can never fire for a bare yes** — even when bro itself just asked "Want me to take a look at that?". Consent is not recognised as a request, so nothing converts the accepted proposal into an Effect.

## The fix, in order

### 1. The invariant (the general fix — three incidents today share this shape)

**A reply claiming a hand-over must have a released effect or a pending receipt.** Enforce it at the commit, not in the lint:

- If `d.actions` contains `tool: "route"` (or a `propose` the owner has now accepted) and `d.effects` is empty → **construct the Effect from the action's `destination`**, or do not claim it. The destination is already in the action; the information to fix this is present at the failure site.
- Emit a loud `route_without_effect` model event whenever it fires, with the destination, the reply and whether an effect was built. This class must never pass silently again.
- On a **spec hit**, re-run the release-shaping step (the `2748` block and its neighbours) before committing. A decision built before the final transcript is not finished merely because its words now match — the words matching is exactly when the stale decision is most dangerous.

### 2. Bare-yes consent

`2548` should also fire when bro's previous reply was an **offer** and the owner's utterance is a bare yes — `self.asked and YES_START.match(said)`, the same test `wanted` already uses at `1591`. `self.asked` is exactly the state that knows bro asked. Do not widen `TELL_TO` to include "yes"; that regex means something else (the owner naming a recipient).

### 3. Then the lint

Add the `get/send/pass that to|over to|across to <someone>` family to `honesty.DELIVER`, with eval cases both directions. This is **third in priority** on purpose: catching the lie in the lint leaves the owner's request unserved, and the invariant above actually serves it.

## Verification

1. Replay turns 9–10 verbatim: the "Yes" produces **one hub item** for `top`, `effects` non-empty, and no `route_without_effect` event.
2. Force a spec hit whose decision carries `route` + empty effects: assert an effect is built (or the reply is downgraded) and the event fires.
3. `honesty.unbacked("I'll get that to the bro agent.", [], [])` → a finding; with a route effect → `None`.
4. A bare "Yes" with **no** prior offer still does nothing — the fix must not turn every affirmation into work.
5. Existing delegation tests unchanged.

## Not a task

The owner said "Yes" to *"Want me to take a look at that?"* — bro's own offer about **bro's own routing behaviour**, destination `top`. Whatever the fix produces should be bro's own work (its dev), not a prescient row unless the owner named a project. Check where `top` resolves before asserting a project in the test.
