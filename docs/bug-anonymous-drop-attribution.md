# Bug: any POST without `by` is recorded as an owner drop (prescient + bro)

Found while chasing two silent drops. **Reproduced.**

## Symptom

Two real owner tasks went `working → done(dropped)`, both recorded `by=owner`, and the owner never clicked anything:

```
tk-479f4621c4cd  thor-voiceai/coordinator  queued 14:02:46 → working 14:03:36 → done(dropped) 14:07:16
tk-59201a566bd2  heinzel/coordinator      done → working 14:11:03 (a restore) → done(dropped) 14:11:48
```
Each drop landed ~45 s after the task entered `working`. Both tasks are real work, not test rows.

## Root cause

`bro/server.py:233`:
```python
by = str(b.get("by") or "the owner")
```
Any caller that POSTs `/api/tasks` without `by` is **attributed to the owner**. That default then satisfies prescient's guard:

```python
# prescient/tasks/store.py:341
if resolution == "dropped" and by != "owner":
    raise ValueError("only the owner drops a task")
```

So the guard that exists to prevent exactly this — something other than the owner dropping a task — is bypassed by a *default*, not by a claim.

## Reproduction (done, on the live hub)

```
$ curl -s -X POST localhost:8766/api/tasks -H 'Content-Type: application/json' \
    -d '{"action":"drop","id":"tk-bcf25d8f53f1"}'      # no "by"
$ sqlite3 data/tasks.sqlite3 "select from_state,to_state,by from events where item_id='tk-bcf25d8f53f1'"
queued|done|owner
```
A request with no provenance at all becomes an owner-authored drop in the permanent event log. (Probe row deleted.)

## Why it matters beyond these two tasks

The event log is the audit record the whole cut-over depends on: `by` is how the owner's decisions are distinguished from agents' and the harness's. A default that says "owner" makes the log **unfalsifiable in the wrong direction** — it invents owner intent. That is worse than a missing value, because nothing downstream can tell the difference later.

Corollary: prescient's "only the owner drops" rule is now provably unenforced for this path.

## Fix — prescient (the guard must not trust the caller)

- `store.done(..., "dropped", by=...)` already refuses non-owner. It also needs to refuse a **missing/absent** `by` rather than inheriting bro's default: the HTTP layer must not pass `by` through when the client didn't send one. Change `server.py` to read `b.get("by")` and pass `None`/`""` through so `store` raises, instead of substituting a role.
- Decide one rule and state it: a drop with no provenance is refused (400, "say who is dropping it"), because an unattributed drop is exactly what the guard exists for. Do **not** default it to `harness` either — that silently reclassifies owner work as machine cleanup.

## Fix — bro (stop inventing provenance)

- `bro/server.py:233` must not default `by` to `"the owner"`. Send the real actor, or send nothing and let the hub refuse.
- The tray/dock already knows its actor: the owner's own click path should send an explicit owner token, and every other caller (auto-ready, agents, the voice bridge) must send its own identity. If a caller cannot say who it is, it must fail loudly — an anonymous write is a bug, not a permission.
- Audit every `taskhub.move(...)` caller for a missing `by`.

## Verification

1. POST a drop with no `by` → 400 and **no** event written. Show the empty event table for that id.
2. POST a drop with `by: "owner"` → succeeds, event says `owner`.
3. POST a drop with `by: "harness"` → refused by prescient (`only the owner drops a task`), event not written.
4. Every existing caller in bro passes an explicit actor; grep shows no `or "the owner"` default remains.
5. The two damaged tasks: `tk-59201a566bd2` reopened to `working` (real work: "Put this in Heinzel's inbox, the boss fight needs a second phase"); `tk-479f4621c4cd` reopened too — both were dropped without their owner's say.

## Still unknown

I have not identified which caller made those two drops. The default is the mechanism that allowed them (and I reproduced an anonymous drop through it), but the specific POST isn't in any log I have — bro serve was restarted at 14:20:49, after both. Adding request logging to the dock is worth doing so the next occurrence is attributable.
