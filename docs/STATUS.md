# Status: .dotfiles
Updated: 2026-11-03 13:00 (Europe/Berlin)

## Now
- Nothing in flight — the task-hub cut-over is complete and verified. Clean checkpoint.

## Next
- Wave 5 finish: remove bro's local task storage (the archive is written and gitignored).
- Watch the first real week of hub usage; the auto-task loop rule is live but young.

## Waiting on the owner
- Nothing blocking.

## Blocked
- Nothing.

## Recently landed
- **Task hub is live.** prescient owns tasks (SQLite store + enforced state machine + HTTP + CLI); bro is a client behind `TASK_HUB=prescient`; Trello is the async audit log. bro's old store is frozen and archived.
- **One route, one delivery path, one resolver.** Coordinator inbox = `state=queued&target=coordinator`; nudges go through prescient's hardened `_deliver`; the plugin's icon diagnostics read prescient's `{status, why}` (ranks v2, version-gated).
- **All panes on v34**, sessions resumed; agents instructed to use `prescient task start|ready` (bro's verbs forward for one release).
- **Three hub bugs found by smoke-testing**, not by assuming: a dropped hub dispatch in the plugin's auto-task path (local store kept being written), env-only switches invisible to the herdr-launched daemon, and a self-referential auto-task loop (fixed by a rule: a turn about the task system never opens a task, and tool *arguments* count as the signal).
- **Auto-task re-enabled** with that rule; `--explain` answers "why is my icon like this" from one source.
