# GO: task-hub build, all projects

Owner: "coordinate all the work across all the projects with their omp and claude instances."
This is the dispatch brief for every coordinator. Read with `docs/design-task-hub.md`, `docs/spec-task-hub-revisions.md`, `docs/omp-peer-delivery-contract.md`, and your own build plan.

## Owner decisions (final, closing A3 + the threshold)

1. **A3 wording.** bro **promises** at create: *"I'll get that to the <project> coordinator."* It never says "on my list" unless `nudged == "ok"`. On `pending` it says nothing further. On `failed` it says so plainly and offers a retry **only when `retryable`**. `create()` returns `nudged: ok|pending|failed` + `retryable`; the item carries both so the owner's retry button is honest.
2. **`undelivered` threshold = 10 minutes**, and **bro never speaks an `undelivered` line unprompted** — the tray/board shows it; bro answers only when asked.
3. Fleet calls (destinations with `project` empty): `plan`/`tweak` → `prescient`; `top` → `bro`; else refuse and ask.

## Waves (do not start a wave before the previous one reports)

**Wave 1 — prescient (coordinator omp-v31-wdp7 + its claude):** steps 1-3 of the build plan.
store + state machine + tests; library ops; HTTP `/api/tasks` + `/api/tasks/ranks`; CLI; `import-bro` (fixups logged, quarantine list, historical events `synced_at` SET, read `ORDER BY at, id`). **Nothing reads it yet.** Acceptance: the spec's test list, plus a live add/list with the server stopped and running.

**Wave 2 — bro (coordinator omp-v31-wdp5 + its claude):** `bro/hub.py`, `Destination.role`, the project fallback chain, call-site switch, HTTP forwarder, bulk `clear` op wiring, `TASK_HUB=local|prescient`, tests. **Still defaulting to `local`.** Acceptance: existing suite green under `local`; hub path demonstrated against the now-live prescient service on a scratch project.

**Wave 3 — cut-over day (all three, same day, coordinated by me):**
- bro flips `TASK_HUB=prescient`; `bro task …` becomes the HTTP forwarder with the deprecation line.
- dotfiles: instructions switch `bro task` → `prescient task` in `config/omp/context-files/APPEND_SYSTEM.md` + `config/claude/CLAUDE.md`, the two-channels wording updated per design §4, VERSION bumped, panes rolled.
- Lifeview plugin: create/ready through `prescient task`, drop its copied tables **only once** prescient serves `{status, why}`.
- Verify end-to-end: a voice hand-off → queued item → coordinator nudged → `start` → `ready` → green icon.

**Wave 4 — prescient:** `{status, why}` + rank publishing; trello replicator draining the outbox.

**Wave 5 — cleanup:** bro deletes storage after a quiet week (keeping `footer`, `NOT_DONE`, `dests_for`).

## Rules for every worker
- One wave per coordinator at a time; report a one-paragraph result + test output when a wave lands.
- No cross-repo edits: prescient touches prescient, bro touches bro, only dotfiles touches dotfiles. Cross-cutting changes go through me.
- Commit locally per repo etiquette; **do not push** without my say (cut-over day is the exception).
- If a spec detail proves wrong mid-implementation, stop and message me rather than inventing a variant.
