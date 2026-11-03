# Spec revisions after coordinator review (2026-11-03)

Both coordinators reviewed the task-hub design. **Every finding below is adopted unless marked otherwise.** This file is the delta; the specs stay authoritative where they are not contradicted here.

Sources: `~/.omp/agent/sessions/-Desktop-personal-repos-prescient/*/local/design-review-task-hub.md` and `bro/docs/task-hub-bro-review.md`.

---

## A. Corrections to the design (owner may want to weigh in on A3)

**A1. `target` is a role enum, not derived from `Destination.depth`.**
bro's real constructions put **every project agent at depth 2** — the project's Claude *and* its coordinator (`voicebridge.py:501,538,546`). My "depth 2 → coordinator, depth 3 → dev" rule would label every project's Claude a coordinator.
**Fix:** map from the **id prefix** (`coordinator:` → `coordinator`; `claude:` / `agent:` → `dev`; `top` → `dev`) **and** add an explicit `role` field to `Destination` so nothing is inferred from depth. (bro owns.)

**A2. `project` needs a declared fallback chain** for the voice hand-offs whose `Destination.project` is empty:
`plan`/`tweak` → `prescient`; `top` → `bro`; else `Destination.project`; else **refuse and ask the owner** rather than creating an item with a guessed project. (bro owns; hub enforces `NOT NULL`.)

**A3. Synchronous delivery outcome — a real design gap.** ⚠️ *Owner decision needed.*
bro speaks the receipt **in the same turn** (`agent.py:381`), and `honesty.ON_LIST` only permits "on my list" after a real delivery — the layer exists because bro twice claimed delivery it hadn't done. `hub.create` returns an id, not an outcome. Options:
- **(i) Optimistic + honest failure** (recommended): bro says a *promise* ("I'll get that to the heinzel coordinator"), never "on my list". If the nudge fails, the item is `undelivered` and bro says so — but only when asked, not unprompted (see A5).
- (ii) Hub returns a `delivered: bool` on create (it can, if it nudges synchronously and reports the omp-peer exit code) — restores today's guarantee without a queue.
Recommendation: **(ii) for the exit code + (i) for the wording** — i.e. the hub reports `nudged: ok|pending|failed`, bro promises at create, and speaks failure only on a later prompt.

**A4. `POST /api/tasks {op: clear}` is required.** bro's bulk clear (`tasks.clear`, `CLEARED`, `/api/tasks/clear`) selects by project+targets, protects `working`, returns `left_working`, and is idempotent with a history step. Per-item `done(cleared)` would turn one turn into N round-trips and lose the "left 3 running" line. Add the op returning `{cleared, ready, left_working, ids}`.

**A5. `undelivered` must not become chatter.** bro should never speak an undelivered line unprompted; the tray/board shows it, and bro answers only when asked. (Owner's earlier "still trying" objection.) The reaper still marks it.

**A6. The reaper's 10-minute rule contradicts the doorbell's "only while idle".** An item created while the coordinator is mid-turn would go `undelivered` while delivery is *correctly* waiting. **Fix:** `reap()` consults the agent's live state (via the same resolver) and only ages items when the target has been idle and has not fetched the queue. Concretely: mark `undelivered` only if the target has been idle for the whole window *and* the item is still `queued`.
Also: **the reaper needs a named tick.** Today's only periodic loop is the tweak dispatcher (`while True` + `sleep(10)`). Reuse that loop (it already runs in the server) and make `reap` idempotent and cheap under WAL.

**A7. `retry` is explicit-only.** `undelivered → queued` happens solely via an explicit `retry` (owner/agent); the reaper never re-queues. One path, written down.

**A8. `park()` must require a `card`.** A parked item without a Trello card makes the replicator silently drop it. Enforce at `park()` (and let `park(card=…)` create/find the card first).

**A9. `reopen()` clears `resolution`** (keeps seven states), and the "not quite" **note is preserved** in the event — that's the interesting part of the audit.

**A10. `list()` needs a monotonic order.** Add `seq INTEGER` (autoincrement per transition) and order by `(updated, seq)`; several transitions within one second are normal.

**A11. Trello outbox must never hold the write transaction.** `sync_trello` drains in batches, marks `synced_at` after the call returns, and tolerates a crash by re-sending (idempotent via the event id in the comment text). Confirmed as a hard rule.

**A12. Import corrections:**
- `project` from the **agent's cwd**, never bro's `project` field (bro files its own hand-offs as `project: "bro"`; `142413a` fixed the same bug for try buttons).
- **Not-running agents**: no cwd to resolve → put the row on a **quarantine list** and report it; do not invent a placeholder project (violates `NOT NULL project` semantics).
- Events replay in file order but must be **read** `ORDER BY at, id`; historical events import with `synced_at` set (do **not** replay a year of history into Trello) — document that choice.
- The real fixup count is computed at import time, not the "61 known cases".

**A13. `GET /api/agent-board` must keep its shape through the cut-over.** This is the page's *only* read path (`agent_board.py:340-370`, 2 s memo). Before the source swaps:
- extend `BRO_STATES` with `created`/`parked`/`undelivered` or items vanish from the column;
- decide tweaks: they stay in `tweaks.json` (their own lifecycle) and are **merged at the board layer**, not migrated — the hub's `list()` must not pretend to own them;
- `create()` is atomic-as-queued in what `board()` exposes (a brief `created` state is a third state the page has never rendered).

**A14. Publish the rank table as data.** `GET /api/tasks/ranks` so the page and the dotfiles plugin read **one** source instead of the plugin re-deriving `AG_RANK`. `why` must be a **spoken sentence**, not a state name.

**A15. `{status, why}` shape** (needed before the plugin deletes its tables):
```json
{"agent": "<name>", "project": "<repo>",
 "status": "working|blocked|ready|queued|idle|...",
 "why": "one plain sentence the owner can hear",
 "rank_table_version": 1}
```
`status` is **nullable-safe**: an agent with no items and no signal is `idle`, never `unknown`.

**A16. Role resolution has one implementation.** `--mine`/`target` resolution must reuse prescient's existing `agent.resolve()` (`agent.py:41`), not a second resolver — a rename already bit us today (`ORCHESTRATOR` → `83173fa`).

**A17. `bro task` forwarder goes over HTTP**, never the git-toplevel CLI — agents run it inside *their* repo, so `project` would be re-derived wrongly. Keep it one release, printing the deprecation line.

**A18. Keep bro's logic, delete only its storage.** `footer()` (coordinator START_IT context), `NOT_DONE` (verdict parsing), `dests_for` (project→dests attribution) survive in some form. Deleting them is a behaviour regression, not a cleanup.

**A19. `TASK_HUB` switch guards:** one authoritative store per process (assert the other is not written); reads follow the switch (no mixing local history into "I have three open"); **fail closed** (hub unreachable while `prescient` → say so, never fall back to local); log the mode at start and in every turn record; import idempotent, file-marked, refused while the hub is live; short timeouts (≤3 s) so a voice turn can never block barge-in.

---

## B. Ownership (agreed)

| Work | Owner |
|---|---|
| `prescient/tasks/` store + machine + tests, HTTP ops, CLI, `import-bro`, board swap, `{status, why}`, rank endpoint, trello replicator | **prescient coordinator** |
| `bro/hub.py` client, call-site switch, HTTP forwarder, `Destination.role`, project fallback chain, clear op wiring, removal pass | **bro coordinator** |
| `omp-peer` exit-code contract doc; instructions (`bro task`→`prescient task`, the two-channels reword); lifeview plugin switched to `prescient task` + reading `{status, why}`; deleting the plugin's copied tables | **dotfiles (me)** |

## C. Revised order (unchanged shape, two additions)

1. prescient: store + machine + tests (no HTTP).
2. prescient: library ops + HTTP (`/api/tasks`, ranks) + CLI; **A13's `BRO_STATES` extension lands in the same PR** as any board-source change.
3. prescient: `import-bro` (quarantine list, fixups logged, history not replayed to Trello).
4. **bro: `hub.py` + `Destination.role` + project chain** behind `TASK_HUB=local|prescient` — the switch is the cut-over lever.
5. cut-over day: bro flips to `prescient`, `bro task` becomes the HTTP forwarder, **and the dotfiles instructions change in the same day** (agents' instructions still say `bro task`).
6. prescient: `{status, why}` + ranks published; dotfiles plugin switches and deletes its tables.
7. prescient: trello replicator. 8. bro: delete storage after a quiet week; keep A18's logic.

## D. Still open for the owner
1. **A3** — the delivery promise wording (recommended: hub reports `nudged`, bro promises at create, speaks failure only when asked).
2. The `undelivered` threshold: 10 minutes stands for harness items; for voice hand-offs bro never speaks it unprompted (A5).
