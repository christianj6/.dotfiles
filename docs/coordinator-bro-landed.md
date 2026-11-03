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

---

## Gap 3, verified: `delegate_to` bypasses the coordinator for bro's own work

The coordinator flagged this and it is real. Independent check of `voicebridge.py:3202`:

```
calls dev_agent: True
calls dev_id:    False
  -> bro-own work in delegate_to returns BRO'S CLAUDE, skipping bro's coordinator
```

`delegate_to` ends with:

```python
if project and (dest := self.handler_for(project, stack)) is not None:
    return dest                       # a named/talked-about project: coordinator-aware, correct
if not about_bro:
    return None                       # asks which project - correct
a = dev_agent(self.agents())          # <- bro's own Claude, never dev_id()
return agent_destination(a) if a is not None else None
```

So every path that goes **through a project** is already coordinator-first; only the `about_bro` path skips it. That is the same shape as gap 1 and it is why the fix belongs in one place.

### Why this is the one that would have silently defeated the change

`delegate_to` is called from `_needs_task` (`:2970`), i.e. for **implied** tasks — "if there's an implied task you should just start delegating that". `handler_for` is bypassed exactly when the owner's words are about bro itself and name no project. So:
- a **status** ask → `handler_for` → coordinator ✔ (this is why `99c165a` appeared to hold)
- an **implied task about bro** → `dev_agent` → bro's Claude ✘

My earlier acceptance of `99c165a` was therefore narrower than I stated: I verified the precedence **inside `handler_for`** and did not verify every caller. That is my error, and it is the same class as the `1+N` mistake — checking the function and inferring the system.

### The complete fix, now three sites with one rule

Every place that selects a destination for **bro's own** work must ask the same question, in this order:

1. a project (named or recently talked about) → `handler_for(project, stack)`
2. bro's own project → **`dev_id()` first**, then `dev_agent()` as the fallback

Sites: `_command` explicit work (`:2904`, gap 1), `delegate_to` (`:3217`, gap 3), and any future one. **Better than fixing three call sites:** put the rule in one helper — e.g. `own_work_dest(stack)` returning `dev_id()`-derived coordinator else `dev_agent()` — and have all three call it. Three copies of a precedence rule is how the next one drifts.

And the test must be an implied-task-about-bro case, not a status case: `"when you're in standby, fix that"`-shaped input, asserting the dest is bro's **coordinator**. A status-ask test passes today and proves nothing about gap 3.

---

## CORRECTION: my gap-3 diagnosis was wrong, and it was the exact error my new rule names

The coordinator checked my claim before accepting it. It does not hold.

`dev_agent()` does **not** return bro's Claude. `is_dev()` (`voicebridge.py:84`) is:

```python
def is_dev(a: dict) -> bool:
    """Is this herdr agent bro's coordinator (the orchestrator)?"""
    if DEV_AGENT:
        return a.get("name") == DEV_AGENT
    if a.get("name") == "orchestrator":
        return True
    return a.get("agent") == "omp" and Path(a.get("cwd") or "").name == BRO_REPO.name
```

So it returns the **omp pane** — verified at runtime: `dev_agent -> omp-v34-wdp5 | kind: omp | cwd: .../bro`. `dev_agent()` has always *been* `dev_id()` in substance. My sentence "`delegate_to` returns bro's Claude, skipping bro's coordinator" was **wrong**.

**How I made the error is the point.** I read the *name* `dev_agent` and inferred "Claude". I never read `is_dev`'s predicate. That is precisely the failure the `fixed-claim-call-sites` rule describes — I checked that `dev_id()` was absent from the call site and concluded the coordinator was bypassed, without checking what the function I *did* see actually returns. Absence of one name is not evidence about a behaviour. My rule's own tell applies to me: a claim with no predicate in it.

The coordinator's characterisation is the accurate one and I am adopting it rather than restating mine: **what was actually missing was `coordinator:bro` (the hub-shaped destination), the Claude fallback when neither coordinator form is available, and the de-duplication.** The bug was smaller than I described; the fix is larger and better than I proposed.

## The build — read in source

`own_work_dest(stack, project)` at `:2188`, precedence in the docstring, **eight** occurrences (definition + seven call sites). It is better than my proposal:

```python
if project:  return self.handler_for(project, stack), False
if (c := self.bro_coordinator(stack)) is not None:  return c, False          # coordinator:bro
if (a := dev_agent(self.agents())) is not None:     return agent_destination(a), False   # the omp pane
claude = ...                                                                  # only now, bro's Claude
return (agent_destination(claude), True) if claude is not None else (None, False)
```

A genuine three-tier fallback — hub destination, then pane, then Claude — and it returns **whether it fell back**, which is what lets bro say honestly who it went to. I proposed a two-tier helper and would have collapsed the distinction between "the coordinator took it" and "the Claude is covering".

The `_needs_task` tail rewrite is gone, so an implied task can no longer be rewritten back to a Claude after the fact. And the which-slot fix means "it's for you" hands on only for `task`/`filing` — a status or question intent can no longer be converted into a hand-over by the clarification. 653 green.

---

## `own_work_dest` — the four return paths, verified by driving the real method

Not inferred from the source. I constructed the four states and called it:

| State | Returns | `fell_back` |
|---|---|---|
| `coordinator:bro` available | `coordinator:bro` | **False** |
| `coordinator:bro` unavailable, omp pane running | `agent:omp-v34-wdp5` | **False** |
| no coordinator, no omp pane, bro's Claude running | `agent:claude-v2-wdp6` | **True** |
| nothing running | `None` | **False** |

Exactly the contract the docstring claims, and the flag is correct in the only place it should be: the Claude case. So bro's honest line can distinguish *"the coordinator took it"* from *"the Claude is covering"* — which was the design point the two-tier proposal would have lost.

## The correction is now consistent across all four records

My wrong version existed in three places; all three now carry the corrected account rather than a silent rewrite:

- `docs/coordinator-bro-landed.md` (mine) — the correction, with how I made the error
- `config/omp/rules/fixed-claim-call-sites.md` (mine) — added as the rule's fourth instance
- bro's spec `3a14784` (the coordinator's) — rewritten with the same reasoning

The coordinator rewrote its spec rather than leaving the wrong version for the next reader, which is the right instinct: a corrected conclusion with an intact wrong rationale is how the same mistake gets repeated.

## Where this leaves the day

**Landed and verified:** privacy guard push-time hole closed (push blocked on a leak, clean push passes, mid-history leak caught); `coordinator:bro` live and served; the flip reaching the omp pane; `own_work_dest` with its four paths; listening mode proven on the real mic; the claim-without-effect class pinned by regression tests.

**Routed, open with prescient:** receipt wording ("that one's yours"), the phrase assertion ("the bro coordinator" → `coordinator:bro`, never `agent:claude-*`).

**Deferred by the owner:** the mic observation after `3c483b0`.

**Still unbuilt, in flight:** the which-slot/none-reachable/classifier-reorder build.
