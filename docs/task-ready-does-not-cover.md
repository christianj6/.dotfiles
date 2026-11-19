# TASK: `ready` does not count as covering, so the owner's own "not quite" opens a second card

Follow-on to the duplicate-task work (`docs/task-fix-duplicate-tasks.md`, pushed in
`f0c715d..eb05870`). That fix removed the *duplicate daemon*. This is a **second,
independent** way to get a card about work that already has one — and the owner hit it
the moment he pressed "not quite".

## Observed

Owner pressed **"not quite"** on `tk-5edb44ae05ee` ("just push it"). The harness then opened
`tk-84a4a895f73b`, an `auto:` card for the same work, and the owner had to drop it 28 s
later.

The timeline, from the hub's own events:

| time (UTC) | event |
|---|---|
| 13:56:35 | `tk-5edb44ae05ee` → `working` |
| 13:57:38 | `tk-5edb44ae05ee` → **`ready`**  ← the owner's reopened feedback |
| 13:57:42 | `tk-84a4a895f73b` **created** — 4 s later, same project |

## Cause

`config/herdr/plugins/lifeview-fallback/lifeview.py:138`

```python
COVERING = ("created", "queued", "working", "open", "sent", "reopened", "noted")
```

`ready` is **not** in `COVERING`. The covering check (`covering_items`, `:937`, called at
`:1552` before any transcript read) therefore found no open item for the project — the only
open item was in `ready` — and `autotask_check` returned "work session: … no task covering
it". So a second card was opened for work that already had one.

**Why `ready` was excluded, and why that is wrong here:** excluding it stops a *completed*
item from suppressing the next piece of work, which is right. But `ready` is also exactly
the state the owner's own verdict puts a card in ("not quite" → reopened → agent picks it
back up → `working` → `ready`). So the one state that means **"the owner says look at this
again"** is the one that fails to cover the work it just asked for.

## Fix

`ready` must cover, without letting a stale finished card suppress genuinely new work.
Distinguish by **recency/attribution**, not by dropping the state:

- Add `ready` to `COVERING`, and
- treat a `ready` item as covering only when it is **recent** — bounded by a constant
  (e.g. the same window the ready path already uses, `JUST_DONE_S`-scale or a documented
  `COVERING_READY_S`) — **or** when its `origin` is `owner` (the owner's verdict is the
  strongest possible statement that this work is live).

Pick ONE rule, document it in the constant's comment, and make the timeline above a test:
the 13:57:38 `ready` must cover a turn at 13:57:42. The pre-existing behaviour that a
long-since-ready card does not suppress a new unrelated task must **also** stay green —
write that test too, so the fix is not a trade of one bug for another.

Also: `hub_state(t)` is what `COVERING` is compared against, so confirm the hub reports the
owner's reopened item as `ready` (it does here) and not something else — if bro's list is in
play (`tasks_of` fallback), `BRO_STATES` maps `ready` → `ready` too, so one addition covers
both paths.

## Acceptance

1. Replay the timeline: a project with one `ready` item created/updated at T covers a turn at
   T+4 s → **no new card**. Prove it with a test.
2. A `ready` item older than the window does **not** cover a turn for a different piece of
   work → still opens a card. Test.
3. An owner-origin `ready` item covers regardless of age. Test.
4. The daemon's own duplicate protection stays: one task per turn, `self.created` marker
   unaffected.
5. `python3 config/herdr/plugins/lifeview-fallback/test_lifeview.py` green, with the new
   cases named for the states they pin.
6. Live check: the owner's next "not quite" on an `auto:` card does **not** create a second
   card — state the command you would run to confirm, or confirm it if a real verdict occurs
   while you work.

## Rules

- This is a covering-rule fix, not a dedupe-by-title fix. Do **not** add title/text matching:
  two genuinely different requests can carry similar words, and suppressing the second is
  worse than allowing a duplicate. The `self.created` session marker already handles the
  same-turn case.
- Do not touch prescient's store. The drop guard (`only the owner drops a task`) is correct
  and stays.
- Commit locally. Do not push.
