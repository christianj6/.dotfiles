# Listening mode round-trip: CLOSED — and one new defect found behind it

Owner ran it on the real mic, run `20261103-154353` (core pid 45198). I verified everything from the telemetry, not the narrative.

## The round-trip is proven

| Step | Evidence (event, seconds into the run) |
|---|---|
| enter | `tier` ACTIVE→LISTENING @ 63.9 s, phrase "okay, um let's try it uh get into listening mode" |
| hold 1 | `final` "Okay, this is a test" @ 73.2 s → `listening_held {"held":1,"words":5}` |
| hold 2 | `final` "Okay speaking again" @ 78.9 s → `listening_held {"held":2,"words":3}` |
| hold 3 | `final` "Okay, that's enough" @ 82.2 s → `listening_held {"held":3,"words":3}` |
| close | `final` "Okay, I'm done" @ 86.9 s → `listening_closed {"held":3,"phrase":"i'm done"}` → `tier` LISTENING→ACTIVE, `in_from_ms` 23 050 (23.0 s) |
| one turn | `turn_ended {"rule":"agree","words":11}` @ 86.9 s — and the turn text in `turns-*.jsonl` holds all three thoughts newline-joined |

**Zero effects in the stretch.** `task_hub_effect` count for this run: **0**. All 16 in today's file belong to earlier runs (13:36–14:20). Hub newest row still 14:43; nothing created. Effect-free, as required.

The tier also showed through prescient's forward as `{'tier':'LISTENING','state':'IDLE','running':true}` — the object the page actually renders.

## NEW DEFECT: bro claims a hand-off it never made

At **165.8 s** the owner said "Yes" (consenting, after "No um give it to you and then it might need to be routed"), and bro replied:

> **"I'll get that to the bro agent."**

- `effects` for that turn: **`null`**
- `task_hub_effect` for the whole run: **0**
- hub rows created after 14:43: **none**

So the reply **claims a delivery that never happened**, and `honesty.unbacked()` returns `None` for it:

```python
unbacked("I'll get that to the bro agent.", [], [])            -> None   # should flag
unbacked("I'll get that to the bro agent.", [], [{'target': 'agent:bro'}]) -> None
```

The honesty lint does not cover this phrasing. `DELIVER` (`honesty.py:23`) matches `sent|passed|told|asked|filed|forwarded|handed over`, and `ACTION` (`:64`) matches `i'll (\w+)` — but "**get** that **to** the bro agent" is not in either vocabulary. The nearest is `DOING`'s `get (that|it|this) (going|done|fixed|sorted)`, which requires a participle, not `to`.

This matters more than the misframed summary: it is the exact class of failure the honesty work exists to prevent — the owner believes work was routed, nothing was, and the item is gone from his attention. It is the same shape as the `tk-fcf2134447ac` incident (a real request that produced no answer), now in the opposite direction (a fake delivery that produced no task).

### Fix

1. Add the `get that to <someone>` family to `honesty.DELIVER` — `get (?:that|it|this) (?:to|over to|across to)`, `send (?:that|it|this) (?:to|over to)`, `pass (?:that|it|this) (?:to|along)`.
2. Add an eval case per phrasing, in both directions: unbacked → flagged; with a route effect → clean.
3. **Why the effect was missing at all is the deeper question** — either the routing was refused (and the reply should have said so) or the effect was dropped between the decision and the commit. That needs the decision's own events, not the reply. Do not fix only the lint: a lint that catches the lie still leaves the request unserved.

## Also noted (not a blocker)

- The close summary opened "Got it — you tested the listening mode...", which misframes "Okay, that's enough" as a test report. The mode is right; the turn-framing is a topic-proxy concern for later.
- Tooltip says "when you're done", `kept()` says 'say "your turn"'. Both are `ListenClose` phrases; aligning the wording is deferred deliberately, not forgotten.
