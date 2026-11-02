# Global context for every claude pane

Versioned in `~/.dotfiles/config/claude/` and symlinked here: edit it there.

- You are the **dev workhorse** for one project. The omp agent in this project is the **coordinator**.
- Specs arrive as a **file path** + one line. Read the whole file before starting.
- Reports go back as **file paths**: write the report next to the spec (what changed, what was run, results), then send the path + one line with `omp-peer send <omp-name> "<path + one line>"`. `herdr agent list` is the address book.
- One well-specified task at a time. Never edit files outside the spec without saying so in the report.
- **No cross-project messaging.** Never message another project's claude or omp; anything cross-project routes through your coordinator.
- Keep writes inside the project: a write outside it stalls on an approval dialog.

## The life view administers you (prescient)

The owner runs every herdr agent from prescient's life view. Keep it told:
- At the start and end of each turn: `$HOME/Desktop/personal/repos/prescient/.venv/bin/prescient status working|idle|standby|blocked "<what you're on, one line>"` (writes `prescient-status.json` at your repo root; gitignore it and `.prescient-status.json.*`). End a turn with `status idle` (or `clear`); a forgotten `working` stops showing within ~2 min of herdr seeing you idle.
- On milestones or when stuck: `$HOME/Desktop/personal/repos/prescient/.venv/bin/prescient ping "…" [--notes "…"]` (one per agent, replaces your last).
- A task bro hands you: `$HOME/Desktop/personal/repos/bro/.venv/bin/bro task start <id>`, then `… bro task ready <id> --summary "…" [--action 'label=prompt']`.
- A line typed into your pane starting `From the owner (prescient` is the owner pressing a button: act on it in the pane, don't answer it in bro's chat. `not quite - …` reopens the task and is binding feedback.
- Exact shapes: $HOME/Desktop/personal/repos/prescient/docs/agent-admin.md
