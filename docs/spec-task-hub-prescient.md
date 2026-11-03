# Spec: prescient task hub (the service)

Repo: the prescient repo directory. Owner decision: **prescient owns tasks as a service; bro becomes a client; Trello is the audit log.** Full design in `~/.dotfiles/docs/design-task-hub.md` — this spec is the implementation contract for the prescient side. Read that doc first; where this spec and the doc disagree, the doc wins and you should raise it.

## Module: `prescient/tasks/`

Follow the conventions already in the repo (match `gantt/inbox.py` for storage style and locking, `gantt/server.py` for HTTP handlers, `cli.py` for argparse subcommands). No new dependencies — stdlib `sqlite3`.

### Files
- `prescient/tasks/__init__.py` — public API, re-exports.
- `prescient/tasks/store.py` — SQLite store + the state machine.
- `prescient/tasks/api.py` (or handlers inside `store.py` if smaller) — the operations.
- `prescient/tasks/sync_trello.py` — the replicator worker (step 5; may be a stub in this pass, see Order).
- `tests/test_tasks_store.py`, `tests/test_tasks_api.py` — plain-pytest, matching the existing `tests/` style.

### Store
`data/tasks.sqlite3` (gitignored owner data; confirm `data/` is ignored — it is). Two tables:

```sql
CREATE TABLE items (
  id TEXT PRIMARY KEY,            -- "tk-" + 12 hex, like today's ids
  text TEXT NOT NULL,
  project TEXT NOT NULL,          -- repo toplevel basename, REQUIRED
  target TEXT NOT NULL,           -- 'coordinator' | 'dev'   (a role, never a herdr name)
  origin TEXT NOT NULL,           -- 'owner' | 'agent' | 'harness' | 'bro'
  state TEXT NOT NULL,
  summary TEXT, actions TEXT,     -- JSON for actions
  card TEXT,                      -- Trello shortUrl, optional
  resolution TEXT,                -- 'accepted' | 'dropped' | 'cleared' when state='done'
  created TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id TEXT NOT NULL REFERENCES items(id),
  at TEXT NOT NULL,
  from_state TEXT, to_state TEXT NOT NULL,
  by TEXT NOT NULL,               -- role: 'owner' | 'agent' | 'harness' | 'bro'
  note TEXT,
  synced_at TEXT                  -- NULL = pending Trello replication (the outbox)
);
CREATE INDEX events_pending ON events(synced_at) WHERE synced_at IS NULL;
```

Use `PRAGMA journal_mode=WAL`, a `BEGIN IMMEDIATE` transaction per transition, and `sqlite3`'s own locking (no fcntl needed).

### State machine (enforce in one table, reject anything else)

```
created  → queued | parked
queued   → working | parked | undelivered
undelivered → queued (retry)
working  → ready | parked | done
ready    → working (owner: "not quite") | done
parked   → queued (unpark) | done
done     → (terminal; reopen only → working, by the owner)
```

Every transition appends an `events` row. `by` must be one of the four roles. `done` requires a `resolution`.

### Operations (library API — every writer goes through these)
- `create(text, project, target, origin, card=None) -> item` — state `created` then immediately `queued` (two events, so the audit shows the hand-off).
- `start(id, by, note="")` → `working`; `ready(id, by, summary, actions=None)` → `ready`; `park(id, by, note)` → `parked`; `unpark(id, by)` → `queued`; `done(id, by, resolution)`; `reopen(id, by, note)`; `retry(id)` (undelivered → queued).
- `list(project=None, target=None, state=None, origin=None, limit=…)` → items, newest-updated first.
- `get(id)`, `events(id)`.
- `reap(now, undelivered_after_minutes=10)` — queued items older than N with no `start` → `undelivered` (invoked by the server's tick and by the CLI).

### HTTP (existing server, port 8765)
- `POST /api/tasks` — body `{"op": "create|start|ready|park|unpark|done|drop|reopen|retry", ...}`; `create` requires `text`, `project`, `target`, `origin`. Respond `{"item": …}`; 400 with a plain error for a rejected transition (mirror `_respond_json` style in `gantt/server.py`).
- `GET /api/tasks?project=&target=&state=&origin=&limit=` → `{"items": [...]}`. **A coordinator's queue is exactly `state=queued&project=X&target=coordinator`** — no queue file.
- `GET /api/tasks/<id>` → item + its events.
- Do not implement `/api/tasks/clear` (bro's is going away); bulk clearing = a `done(cleared)` op per item.

### CLI (`prescient task …`)
Match `prescient status`'s style (`cli.py:224-236`): `--project` defaults to `git rev-parse --show-toplevel` basename, `--by`/actor defaults to `$HERDR_PANE_ID`-resolved role, direct library call under the store (works with the server down).

Subcommands: `add <text> [--project] [--target coordinator|dev] [--origin] [--card]`, `list [--project] [--state] [--mine]`, `start <id>`, `ready <id> --summary … [--action label=prompt]`, `park <id> [--card url]`, `unpark <id>`, `done <id> [--resolution accepted|dropped|cleared]`, `reopen <id>`, `retry <id>`, `from-card <trello url>` (creates a queued item linked to that card).

`--mine` resolves the caller's role from herdr (`herdr agent list` by `$HERDR_PANE_ID` → the agent's cwd → is it the repo's coordinator or a dev pane) — put that resolution in one function and reuse it.

### Migration (one-shot, idempotent)
`prescient task import-bro <path-to-bro/data/tasks.json>`:
- Map states per the design doc §3 (open→created+queued, sent→queued, noted→parked, working→working, ready→ready, reopened→working, failed→undelivered, done→done(accepted|cleared per history), dropped→done(dropped)).
- `project`: keep when sensible; where `None` or pane-derived, fix from the agent's cwd **at import time** (log every fixup: `None → heinzel (from cwd)`).
- Copy `history[]` into `events` preserving `at`/`state`/`by`/`note`; mark those events `synced_at` NULL unless the original task had no Trello link (decide and document).
- Refuse to run twice (a marker row) and never mutate bro's file.

## Order for this pass
1. `store.py` + state machine + tests (the core; no HTTP/CLI yet).
2. Library ops + `tests/test_tasks_api.py`.
3. HTTP endpoints in `gantt/server.py` (thin handlers calling the library).
4. CLI subcommands.
5. `import-bro` with the fixup log.
6. `sync_trello.py`: **stub only** — define the worker entry point and the event→action mapping in a docstring, do not call Trello yet.

## Acceptance
- `pytest tests/test_tasks_store.py tests/test_tasks_api.py` green, covering: every legal transition, every illegal one rejected, `done` requiring a resolution, the outbox marking, WAL/transaction behaviour under concurrent writers (two threads, no lost events), and `reap`.
- `prescient task add` + `prescient task list` work from a repo (project defaults to the repo name) with the server **stopped**; then with the server running, `POST /api/tasks` creates and `GET /api/tasks?state=queued&target=coordinator&project=<x>` returns it.
- `import-bro` run against a COPY of bro's `data/tasks.json`: report how many items imported, how many project fixups, and that a second run refuses.
- Nothing in bro is modified. Nothing outside `prescient/tasks/`, `prescient/cli.py`, `prescient/gantt/server.py`, `tests/`, and `.gitignore` is touched.
- Commit (message starting "tasks:") with the test output; do not push unless the owner asks.

## Report
What you built, test results, the import dry-run numbers, and anything in the design doc that proved wrong or ambiguous as you implemented it.
