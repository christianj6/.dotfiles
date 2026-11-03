# Cut-over result (2026-11-03)

## What is live
- **prescient is the store.** 105 done / 6 ready items; `prescient task …` CLI and `/api/tasks`+`/ranks` on 8765.
- **bro is a client.** `TASK_HUB=prescient`, tray proxies the hub (`/api/tasks` → 111 items, `hub_state` present), hub-down → 503 with `hub_down`.
- **`data/tasks.json` frozen at 12:14:14** — the last local write, before the fix below. Backed up at `/tmp/tasks-pre-flip-1138.json`.
- **All panes rolled to VERSION 34** (prescient, bro, heinzel, thor + their claude panes; sessions resumed).

## Smoke test (live, not mocked)
`create → queued → working → ready → done(accepted)`, each step with `nudged: ok` on the nested-omp path; the life view's `/api/agent-board` and bro's tray both serve the same item. Illegal transitions refused; a create for a project with no running coordinator returns `nudged: failed (retryable)` and the item survives.

## Three real bugs the smoke test caught
1. **`open_task` lost its hub dispatch** when the file was reordered — every auto-task kept writing the LOCAL store after the flip (caught by watching `data/tasks.json`'s hash). Restored; all three hub dispatches now greppable (`aaa6d01`).
2. **Switches were env-only**, and herdr launches the plugin daemon *without* env, so a config-file switch was ignored. `LIFEVIEW_TASK_HUB`/`AUTO_TASK`/`AUTO_READY*` now read env **or** the plugin config file (`18ec379`).
3. **Self-referential auto-task loop**: auto-task fires on any turn with 2+ tool calls — including the coordinator's own work turns (reading the hub, clearing the queue). Each turn spawned a card that nudged the coordinator, whose next turn spawned another: 8 items in ~4 minutes, each describing the previous turn.

## Current posture
`LIFEVIEW_AUTO_TASK=0` on this machine until the loop is designed away. The mechanism is intact and needs one line to re-enable. **The real fix is a rule, not a flag**: auto-task must ignore turns that are themselves about the task system (a turn whose tool calls touch `prescient`/`bro`/the hub), and must never fire for an agent that already has an open item — that is what closes the loop safely rather than turning it off.

## Still open
- Wave 4: `{status, why}` + ranks v2 (built, not published).
- Wave 5: archive `data/tasks.json` → `data/archive/tasks-hub-pre-cutover.json`, then remove storage.
- Auto-task re-enable with the loop rule above.
