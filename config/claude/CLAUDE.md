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
- Do NOT use `prescient ping` unless the owner asks: pings land in prescient's INBOX, and the owner finds them noise. The icon's status is set by `prescient status` alone.
- A task bro hands you: `$HOME/Desktop/personal/repos/bro/.venv/bin/bro task start <id>`, then `… bro task ready <id> --summary "…" [--action 'label=prompt']`.
- **`bro task ready` is what turns your icon GREEN on the life view** (`prescient status` only moves the inner line: idle/working/standing-by; the ring color comes from bro task state). So when the owner hands you work, `bro task start <id>`; when it is done and worth checking, `bro task ready <id> --summary "what landed" [--action 'label=prompt']`. Never mark `done` yourself — the owner reviews (`looks good` / `not quite`).
- A line typed into your pane starting `From the owner (prescient` is the owner pressing a button: act on it in the pane, don't answer it in bro's chat. `not quite - …` reopens the task and is binding feedback.
- Exact shapes: $HOME/Desktop/personal/repos/prescient/docs/agent-admin.md
