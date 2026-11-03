# Design: prescient is the task hub (revision of proposal-work-item-routing.md)

Owner decisions, 2026-11-03, answering the proposal's §4:
- **prescient owns tasks.** bro is an interface (voice), not a store; its task management moves out.
- **States:** created, queued, working, parked, ready, done, undelivered. The proposal's state machine stands.
- **A service rather than per-repo files**, as the default. The owner holds no strong opinion beyond "not bro".
- **Trello is the audit history of all work.** It is not only where parked work goes; it should ideally represent all work. The question is whether Trello runs the state machine, or a local machine is replicated into it.

Everything else in the proposal (one route, one delivery path, one resolver, stable identity) carries over. Below are only the parts these decisions change.

## 1. Where the state machine runs: local, replicated to Trello

Trello stays out of the live loop, for three reasons:
- **Speed:** the life view polls every 2–5 s and the harness ticks every 10 s. Trello's rate limit is about 100 requests per 10 s per token, with 300 ms to 1 s per call.
- **Availability:** with Trello in the loop, an outage or an expired token would freeze every icon and every hand-off.
- **No transition rules:** Trello can't enforce valid state transitions. A card dragged by hand would bypass the machine.

So: **prescient's local store is authoritative for live state, and every transition is appended to an event log that is replicated to Trello asynchronously.** Trello gets the complete, durable record. Live behaviour never waits on it.

## 2. The service (prescient)

**Module:** `prescient/tasks/`. Every writer goes through one library: the HTTP server, the CLI, and the board.
- **Store:** SQLite in `data/` (gitignored owner data, stdlib).
  - Table `items`: current state.
  - Table `events`: append-only, one row per transition.
  - This replaces bro's whole-file JSON rewrite. Transitions become transactional, the audit trail is native, and the `events` table doubles as the Trello outbox (a `synced_at` column).
- **Item fields:**
  - `id`, `text`;
  - `project`, explicit and required: the repo toplevel's basename;
  - `target` as a role (`coordinator` | `dev`), never a herdr name;
  - `origin` (`owner` | `agent` | `harness` | `bro`);
  - `state`, `summary`, `actions`;
  - `card`: an optional Trello shortUrl;
  - `resolution` for `done`: `accepted` | `dropped` | `cleared`. Dropped is a kind of done, not an eighth state.
- **Transitions** are enforced in a single table, and `by` is a role:

  ```
  created → queued → working → ready → done
            queued → parked | undelivered;   undelivered → queued (retry)
            ready  → working (owner: "not quite");   parked → queued (unpark)
            any non-terminal → done(dropped) by the owner
  ```

- **HTTP** on the existing server (8765):
  - `POST /api/tasks` with `{op: create|start|ready|park|unpark|done|drop|reopen, …}`;
  - `GET /api/tasks?project=&target=&state=`. A coordinator's queue is just `state=queued&project=X&target=coordinator`, so no queue file is needed.
- **CLI:** `prescient task add|list|start|ready|park|done …`.
  - It calls the library directly under the store's lock, so it works while the server is down.
  - `project` defaults to the git toplevel, the same rule `prescient status` already uses (`cli.py:229`).
- **Delivery:** creating an item makes it `queued`, then the coordinator is nudged with one line through `omp-peer`, never with the task body.
  - If the coordinator hasn't started or parked the item within N minutes, it becomes `undelivered`: visible on the board and retried.
  - This replaces bro's `delivery.py` and pending queue, the doorbell, and the fire-and-forget ask.

## 3. bro becomes a client

- Voice hand-offs call `POST /api/tasks {op: create, project, target, origin: "owner", text}`.
- Voice verdicts ("it's done", "still broken") call `done`/`reopen`.
- bro's "what's on my list" reads `GET /api/tasks`.
- **To remove from bro:**
  - the store and its states, lifecycle and clearing (`tasks.py`);
  - `bro task …` (`cli.py:48-139`);
  - `/api/tasks` and `/api/tasks/clear` (`server.py:86, 127-195`);
  - delivery and pending (`delivery.py`, `voicebridge.py:3280-3361`);
  - the task-state mapping prescient keeps for bro (`agent_board.py:95`).
- **Kept for one release:** `bro task start|ready|done` as a thin forwarder to `prescient task …` printing a deprecation line. Every live agent's instructions still say `bro task`.
- **Migration:** a one-shot import of bro's `data/tasks.json` with this state map:
  - open → created
  - sent → queued
  - noted → parked
  - working → working
  - ready → ready
  - reopened → working
  - failed → undelivered
  - done → done(accepted), or done(cleared) where history says `cleared`
  - dropped → done(dropped)

  Projects are fixed up from the agent's cwd where `project` is None or pane-derived (61 known cases). History is copied into `events`.

## 4. Trello as the audit history, without flooding the board

"All work in Trello" taken literally means one card per item, which would be about 60 harness cards a day on the planning board. Instead, replicate at the right granularity:

| Item | What lands in Trello |
| --- | --- |
| Has a `card` (it belongs to an epic) | One comment per transition on that card ("ready: <summary>", "done: accepted"), plus a checklist item ticked on done |
| `parked` | A real card in the project's backlog list; `card` is set, so later transitions comment on it |
| No card, not parked | Batched: one comment per day per project on a "work log" card, one line per finished item (id, text, resolution, summary) |

- The sync is one-way (local → Trello), idempotent (the event id is in the comment text), and run by a worker in prescient's server draining `events where synced_at is null`. It reuses prescient's existing Trello client (`sources/trello.py`).
- Trello → local is only ever explicit: `prescient task from-card <url>` creates a queued item linked to that card. A card moved in Trello never silently changes a live state.
- **Note:** this revises the "two channels, never mixed" rule in `config/claude/CLAUDE.md` and `config/omp/context-files/APPEND_SYSTEM.md`. The new rule: agents still never write task history into the board, and the hub replicates it. Those instruction files change in the dotfiles step.

## 5. What dotfiles does

- **Instructions:** `bro task start|ready` becomes `prescient task start|ready`, and the Trello rule is reworded as in §4.
- **lifeview plugin:**
  - create through `prescient task add --origin harness` (project from the git toplevel), then `ready`;
  - drop its copied `AG_RANK`/`BRO_STATES`/`COVERING` tables once prescient serves `{status, why}`;
  - stop needing the Desktop bro path.
- **`omp-peer`:** document its exit-code contract, because the hub's nudge depends on it.

## 6. Order

1. **prescient:** the service (store, machine, HTTP, CLI) and the import, running alongside bro's store. Nothing reads from it yet.
2. **bro:** client calls and the `bro task` forwarder. The cut-over day, when prescient becomes the only store.
3. **dotfiles:** instructions and plugin switched over (small, same day as step 2).
4. **prescient:** the resolver publishes `{status, why}`; the plugin's tables are deleted.
5. **prescient:** the Trello replicator.
6. **bro:** delete the forwarder and the dead code after one quiet week.

**Open for the owner:** the time before an unstarted item counts as `undelivered`. The suggestion is 10 minutes, since a coordinator mid-turn can take that long.
