# Architecture: oversight vs. planning — two different channels

Owner clarification, 2026-11-02.

## The split
- **bro/prescient tasks = the oversight channel.** An agent uses a task to tell the owner *what it is doing right now* and to hand over something for review. Short-lived, one per unit of work, drives the life-view icons (amber = working, green = ready for verdict). This is the "what is happening" surface.
- **Trello + the repo doc = the planning/coordination channel.** Backlog, epics, decisions, multi-session structure, cross-project coordination. Durable, long-lived. See `rule://` + `skill://issue-tracker-trello` + each project's `docs/DEV_BOARD.md`.

## Consequences for agents (and for the harness)
1. **Never duplicate the plan into a task.** A task's text is the *current unit of work*, not the epic that contains it. If a Trello card exists for the work, the task references it (`<card shortUrl>` in the text/note) rather than restating it.
2. **Tasks are disposable; plans are not.** Closing or dropping a task is routine. Trello/board state should never be inferred from task history, and vice versa.
3. **The harness may create tasks automatically** (auto-task/auto-ready in the lifeview plugin) precisely because they are cheap and ephemeral — it must NOT write to Trello, and must not try to synthesise planning structure.
4. **Coordination between projects happens via coordinators** (`rule://coordinator-network`), recorded in Trello/repo docs — not via task hand-offs between agents.
5. **An agent finishing a chunk of an epic** should: mark its task `ready` for the owner's verdict (oversight), and update the epic's `## Work items` / `## Log` in the repo doc (planning). Both, different channels, no copying between them.

## Where this is recorded
- Global instructions (`config/omp/context-files/APPEND_SYSTEM.md`, `config/claude/CLAUDE.md`): the life-view paragraph should state the split in one or two lines so every agent applies it.
- The tracker skill already owns the planning side; no change needed there.
