# Wave-4 answers: the `{status, why}` resolver (2026-11-03)

Rulings on prescient's sketch. Both findings **accepted**, with the evidence I checked.

## Finding 1 — rank table must merge two vocabularies: ACCEPTED (v2)

`AG_RANK` (`lifeview.py:117`) ranks hub states *and* agent statuses in one table with entries hub v1 lacks (`blocked`, `dropped`, `idle`). Publish v2:

```
ready 0 | undelivered/failed 1 | blocked 2 | working 3 | queued/created 4 |
parked/noted 5 | done 6 | dropped 7 | idle 8
```

`rank_table_version: 2`. The plugin keeps reading the version and refuses to rank against a table it does not know (fail loud, never guess order).

## Finding 2 — a real rank bug in my table: ACCEPTED

The hub stores `dropped` as `done(resolution='dropped')`; my `BRO_STATES` maps it to `dropped` (rank 7), which ranks **below** `done` (6). Live data: **28 dropped / 6 cleared / 60 accepted of 94 done** — a resolution-agnostic resolver would mis-order a third of the board.

**Rule: rank on the EFFECTIVE state.**
- `done` + `resolution='dropped'` → rank as `dropped` (7)
- `done` + `resolution='cleared'` → rank as `done` (6) — clear means "the owner has seen it", which is not the same as abandoned
- `done` + `resolution='accepted'` → rank as `done` (6)

This is a correctness fix, not a preference: the number is derived from `resolution`, never from `state` alone.

## Design point — the resolver reads `agent_board.board()`, not herdr: ACCEPTED

`/api/agent-board` already merges herdr + `prescient-status.json` per agent (`_agents`/`_own_status`). A second herdr/status-file merge inside the resolver would let the plugin and the life view disagree about one agent — the exact `83173fa` class.

**Contract**: `GET /api/tasks/status?project=&agent=` is a thin function over `agent_board.board()`'s rows plus the hub's items:
- agent/project status comes from the board row (already merged, already memoised ~2 s);
- the *rank* comes from hub items only, through `rank_table_version: 2` and the effective-state rule above;
- the response shape: `{agent, project, status, why, rank_table_version}`;
- `status` uses the plugin's vocabulary so `AG_RANK` lookups keep working during migration;
- `why` is one spoken sentence (no plumbing names);
- a project with a running agent and no items is **idle**, never unknown.

## What this unblocks

After the flip, the plugin deletes `AG_RANK`/`BRO_STATES`/`COVERING` and asks the resolver for `{status, why, rank_table_version}`. Until then it keeps its tables — they are already correct on this branch (they map `dropped` explicitly), but they are a *second* copy, which is why the migration is the point.
