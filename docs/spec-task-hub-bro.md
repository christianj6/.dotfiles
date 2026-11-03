# Spec: bro becomes a task-hub client

Repo: the bro repo directory. Owner decision: **prescient owns tasks as a service; bro becomes a client; Trello is the audit log.** Design: `~/.dotfiles/docs/design-task-hub.md` §3. Read it first; where this spec and the doc disagree, the doc wins and raise it.

Depends on the prescient service existing (`POST /api/tasks`, `GET /api/tasks`, `prescient task …`). Until it is live, ship the code paths behind a config switch so bro keeps working: `TASK_HUB=prescient|local`, default `local`, flipped to `prescient` on cut-over day. No Big Bang.

## 1. One client module
New `bro/hub.py`:
- `create(text, project, target, origin="owner", card=None) -> item`
- `start(id, by, note="")`, `ready(id, by, summary, actions=None)`, `park(id, by, note)`, `unpark(id, by)`, `done(id, by, resolution)`, `reopen(id, by, note)`
- `list(project=None, target=None, state=None, origin=None, limit=…)` → items
- `queue(project, target="coordinator")` → `list(state="queued", project=…, target=…)`
- Implementation: HTTP against `http://127.0.0.1:8765` (reuse the URL helper style already in `bro/stack.py`/`bro/triage.py` for the prescient base URL — do not hardcode a second copy), with a single `_call(op, **fields)` that maps JSON errors to a `HubError`. Timeouts short (3 s); a hub failure must never hang the voice loop — raise and let the caller speak a plain line.

## 2. Call sites switched to the hub
- **Voice hand-off** (`bro/agent.py::_deliver` / the `route` action): `hub.create(text=card.text, project=<explicit>, target=<coordinator|dev from the Destination>, origin="owner")`. The `Destination` already carries `project` and a depth — map depth 2 → `target="coordinator"`, depth 3 → `target="dev"`, and take `project` from `Destination.project` (never from the dest string).
- **Voice verdicts** ("it's done", "not quite"): `hub.done(id, by="owner", resolution="accepted")` / `hub.reopen(id, by="owner", note=…)`.
- **"What's on my list"**: `hub.list(project=…)`.
- **Delivery/pending** (`bro/delivery.py`, `voicebridge.py:3280-3361`): delete the send path once the hub is live — creating an item is delivery. Keep `delivery.py` importable only if something else uses it; otherwise remove it and its tests.

## 3. `bro task …` becomes a thin forwarder (one release)
`bro task add|list|start|ready|done|reopen|drop|park` → forward to `prescient task …`, print the result plus one deprecation line: `(bro task is deprecated; use prescient task …)`. Update `bro/AGENTS.md` if it documents the commands.

## 4. Remove (after the forwarder has shipped and the hub is live)
`tasks.py` (store, states, `opened`, `move`, `_project`), `cli.py:48-139` task handling, `server.py` `/api/tasks` + `/api/tasks/clear` (`server.py:86,127-195`), the task-state mapping prescient keeps for bro, and the tests that pinned the old store. Keep the import path alive one release if other code imports it.

## 5. Tests
- `tests/test_hub.py`: the client maps ops → the documented JSON; a hub error surfaces as `HubError` with the server's message; no retry loop in the client (retries belong to the server's `undelivered` state).
- Update the voice tests to assert the hub call shape (mock the HTTP layer, not the network).
- The forwarder prints the deprecation line.

## Acceptance
- With `TASK_HUB=local`: today's behaviour unchanged, all existing tests pass.
- With `TASK_HUB=prescient` and the prescient server up: a voice hand-off creates an item in the hub with the right `project`/`target`/`origin`; a verdict on it moves it; `what's on my list` reads from the hub. Demonstrate with a real request against a scratch project.
- No task state remains stored in bro when the hub is authoritative.
- Commit (message starting "hub:"); do not push unless the owner asks.

## Report
What moved, the switch's semantics, test results, anything that could not be forwarded (e.g. voice behaviour that depended on the old synchronous receipt), and what must happen on cut-over day.
