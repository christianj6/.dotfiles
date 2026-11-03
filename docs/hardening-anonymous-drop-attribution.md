# Anonymous `by` is recorded as owner — hardening, NOT a live drop bug

## Correction first

I initially reported this as "two real owner tasks silently dropped." **That was wrong.** I asked the owner: they clicked those drops themselves in bro's task dock. So:

- There were **no** invented owner drops.
- I reopened two of their deliberate drops by mistake; both are restored to `done(dropped)` with a note saying so. Four tasks total were churned (reopen → re-drop) before I asked.
- My process error: I inferred "silent" from a ~45 s gap and a `by=owner` stamp, then wrote a bug report and repaired the data **before confirming with the only person who could know**. The 4-clicks-in-20-seconds pattern was visible evidence of a human and I read past it, because the narrative I had built already explained it.

Recording that honestly because the same inference pattern would otherwise recur: `by=owner` in the log means the action *was attributed* to the owner, not that the owner made it — but it is also exactly what an owner click looks like.

## What is still true (and verified)

`by` defaults to the owner on both docks:

```python
# prescient/gantt/server.py:588
op, tid, by = b.get("op"), str(b.get("id") or ""), b.get("by") or "owner"
# bro/server.py:233
by = str(b.get("by") or "the owner")
```

Reproduced live: `POST /api/tasks {"action":"drop","id":X}` with **no `by`** wrote `queued → done, by=owner` into the permanent event log.

That default satisfies prescient's guard:
```python
# prescient/tasks/store.py:341
if resolution == "dropped" and by != "owner":
    raise ValueError("only the owner drops a task")
```

So the guard that exists to prevent non-owner drops is satisfied by a default rather than a claim. Today no caller exploits it — but any future caller that forgets `by` will silently produce an owner-authored drop, and the audit log cannot tell that apart from a real click. That is a real weakness in the audit record the cut-over depends on, not a present outage.

## Fix (both sides, defence in depth — not urgent)

- **prescient** `server.py:588`: do not substitute a role. Pass `b.get("by")` through; let `tasks.done` refuse a missing `by`. An unattributed drop is refused (400, "say who is dropping it"). Do **not** default to `harness` — that reclassifies owner work as machine cleanup.
- **bro** `server.py:233`: send the real actor, or send nothing and let the hub refuse. Audit every `taskhub.move(...)` caller: owner clicks send an explicit owner token; auto-ready, agents and the voice bridge send their own identity.
- `_bro_task_write:458` sending `by: "the owner"` is **correct** and must stay — prescient's board is acting for the owner there by construction.

## Verification

1. Drop with no `by` → 400 and **no** event written.
2. `by: "owner"` → succeeds, event says `owner`.
3. `by: "harness"` → refused by prescient, no event.
4. No `or "owner"` / `or "the owner"` default remains on either tasks dock.

Optional: request logging on the docks, so any future anonymous write is attributable.
