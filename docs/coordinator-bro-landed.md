# coordinator:bro — landed, and my sanity-check of the flip (2026-11-03)

prescient `e1ce7aa`, pushed and served (8765 restarted). Verified independently, then checked the consequence the coordinator asked me to sanity-check on bro's side.

## Served destinations — verified against the running server

```
$ curl -s localhost:8765/api/bro-stack/destinations
plan                    depth=1 project=None             available=True
tweak                   depth=1 project=prescient        available=True
coordinator:bro         depth=2 project=bro              available=True   done="I passed it to the bro coordinator."
coordinator:dotfiles    depth=2 project=dotfiles         available=True
coordinator:prescient   depth=2 project=prescient        available=True
coordinator:thor-voiceai depth=2 project=thor-voiceai    available=True
coordinator:heinzel     depth=2 project:heinzel          available=True
top                     depth=3 project=None             available=True
```

Not taken from the report — read from the server the page and the voice core both use.

## THE FLIP — confirmed, and it does what the owner asked

`bro/stack.py:43` `role_of`: `coordinator:*` → `coordinator`. So bro's **own** explicit work now targets a coordinator instead of a dev:

```
coordinator:bro      role=coordinator  on_hub=True  target=('bro','coordinator')
coordinator:heinzel  role=coordinator  on_hub=True  target=('heinzel','coordinator')
top                  role=dev          on_hub=True  target=('bro','dev')     <- unchanged
```

**And the nudge now lands on the omp pane, which is the whole point:**

```
agent_for('bro', 'coordinator') -> omp-v34-wdp5   (pane wD:p5)
agent_for('bro', 'dev')         -> claude-v2-wdp6 (pane wD:p6)
```

Before this change, bro's own explicit work reached `claude-v2-wdp6` directly. Now it reaches `omp-v34-wdp5`, which decides what bro's Claude does. That is the owner's decision ("explicit fix it still to coordinator first") actually in effect, not just specified.

**Behavioural consequence worth knowing:** hub items for bro's own work now carry `target=coordinator`, so they rank and are nudged as coordinator work. Any existing bro item already in flight as `bro/dev` is unaffected — the target is stamped at creation.

## The two notes — my read

**1. Self-forward to "the bro coordinator".** Real. Delivering to `coordinator:bro` asks the orchestrator to hand the card to the bro coordinator, which *is* the orchestrator's own pane. It will almost certainly take it, but the honest framing is that the orchestrator **is** bro's coordinator, so the instruction should read "this is already yours — take it" rather than "pass it to the bro coordinator". One line in bro's orchestrator instructions; I've asked for it.

**2. "bro coordinator" becomes a sayable phrase.** Correct and intended. Worth knowing the failure shape: if the owner says "the bro coordinator" and bro's `named_project` resolves `bro`, it now resolves to a **coordinator** destination rather than bro's Claude — which is the desired behaviour, but it is a behaviour change for that phrase, not just a new name. It should be added to the phrase set deliberately, and the acceptance should assert that "the bro coordinator" reaches `coordinator:bro` rather than `agent:claude-…`.

## Not shadowing — independently checked

- `plan` / `tweak` are `queue` role, so `coordinator:bro` cannot capture them.
- `top` is its own id and still resolves to `('bro','dev')`.
- Nothing in bro resolves a destination by the bare string `bro`.

The coordinator's claim holds on all three.
