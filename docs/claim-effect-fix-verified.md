# Claim-without-effect: fixes landed, verified (2026-11-03)

bro, 594 tests, `tests/test_claim_without_effect.py` 9 passed. Verified by me against the tree, not from the report.

## 1. The invariant — the general fix

`claims_have_effects(d, said, msg_id, spec, turn_id, hit)` (`voicebridge.py:1943`) walks `d.actions`; a `route` with a destination not already in `d.effects` and no error result:

- emits `route_without_effect` with `{turn_id, tools, dests, spec_hit, spec, by, reply}` — so the class aggregates, as asked
- **builds the Effect from the action's own destination** and label
- prints loudly to stderr

Two call sites: `:1986` inside `decide` (the model path) and `:3362` at the commit with `hit=hit is not None` — so **spec hits are covered**, which was the whole point.

Correct boundary: a `propose` is an offer awaiting a yes, so it is **never** built into an effect. The test asserts exactly that (`offer.effects == []`).

I confirmed the forced-hit test is the class, not the instance:
```python
hit = Decision("Yes","tr-10","I'll get that to the bro agent.",[{tool:route, dest:top,...}],[],...)
b.claims_have_effects(hit, "Yes", "tr-10", turn_id=10, hit=True)
assert [e.dest for e in hit.effects] == ["top"]        # rebuilt from the action
assert ev[0]["spec_hit"] and ev[0]["dests"] == ["top"] and ev[0]["turn_id"] == 10
```

And the replay asserts the **release** creates `("bro","dev")` with a `task_hub_effect` — i.e. `top` resolves to bro's own developer, matching the note I gave: it must not become a prescient row.

## 2. Bare-yes consent

Parametrised over the owner's real consent words — `"Yes"`, `"yes please"`, `"go ahead"`, `"Yeah, do it"` — each now yields the offer's Effect. And the negative cases hold: `"Yeah, sure I just need an answer"`, `"yeah no, not that"` produce **no** effect. That second tuple matters: it is the exact utterance from the `tk-fcf2134447ac` incident, so this fix and that one are consistent rather than fighting.

## 3. The lint

```
"I'll get that to the bro agent."    -> deliver
"I'll send that over to Claude."     -> deliver
"I'll pass that across to heinzel."  -> deliver
with a route effect                  -> None
```

## Two false positives I found (pre-existing, not regressions)

I checked against `HEAD` with the changes stashed to be sure these were not introduced today — they flag identically at `3c483b0`:

| Reply | Flag | Verdict |
|---|---|---|
| "Two open. Two are ready for you to try." | `ready` | **false positive** — `READY` matches "are ready", and a read tool result doesn't back it either |
| "I could not reach the hub, so nothing was sent." | `deliver` | **false positive** — a negation that *denies* the delivery is read as claiming it; `_NEG` ("I did not…") doesn't cover "nothing was sent" |

Both are low-harm: the flag triggers a **retry** with `avoid_claim` set, not a wrong reply. But they waste an LLM call (~2 s) on honest replies, and the "nothing was sent" one is the honesty system punishing a *true* statement — worth fixing when someone is next in `honesty.py`:
- `_NEG` should treat "nothing was sent/passed/filed" as a denial.
- `READY` should not match a bare "are ready" describing the owner's own list unless something was actually made ready in this turn.

Not fixed now: out of scope for this spec, and the risk of touching `_NEG` for a lazily-phrased claim is worse than two extra retries.

## State

- bro: 594 tests, committed as `3c483b0` plus working changes (`bro/agent.py`, `bro/voicebridge.py`) — **uncommitted at the time I verified**, so the coordinator may still be finishing.
- Voice 45198 up, serve 44537 untouched, no restart.
- Not yet exercised on the real mic after the fix — the replay is a proof of the code path, not of the microphone.
