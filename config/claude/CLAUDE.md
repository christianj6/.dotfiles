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
- A task bro hands you: `$HOME/Desktop/personal/repos/prescient/.venv/bin/prescient task start <id>`, then `prescient task ready <id> --summary "…" [--action 'label=prompt']` (prescient's venv bin; `bro task …` still forwards for one release).
- **`prescient task ready` is what turns your icon GREEN on the life view** (`prescient status` only moves the inner line: idle/working/standing-by; the ring color comes from the hub task state). So when the owner hands you work, `prescient task start <id>`; when it is done and worth checking, `prescient task ready <id> --summary "what landed" [--action 'label=prompt']`. Never mark `done` yourself — the owner reviews (`looks good` / `not quite`).
- **The harness propagates your state automatically** (herdr plugin `lifeview-fallback`): your working/idle/blocked reaches the icon without you. When you start real work no task covers (2+ tool calls, or one running >90 s), it **opens a task for you** (`auto:` title, by `lifeview-harness`), and when you settle after answering, it marks that task ready (summary = your last message, marked `auto:`). Amber then green, with no CLI calls. So: do NOT `prescient task add` your own task for such work (that would duplicate it). When the owner hands you a task, you may still `prescient task start` it (then `ready` is yours alone; the harness won't green it for you). Your calls are only the judgment ones: `status standby`/`blocked` when you wait on purpose, and `prescient task ready` when a started task is truly worth the owner's check. `python3 ~/.dotfiles/config/herdr/plugins/lifeview-fallback/lifeview.py --explain` says why any icon looks the way it does.
- A line typed into your pane starting `From the owner (prescient` is the owner pressing a button: act on it in the pane, don't answer it in bro's chat. `not quite - …` reopens the task and is binding feedback.
- **Two channels, never mixed**: a bro/prescient task is OVERSIGHT — what you are doing right now, and the thing you hand over for the owner's verdict; short-lived and disposable. Trello and your repo doc (`docs/DEV_BOARD.md`) are PLANNING — backlog, epics, decisions, multi-session structure; durable. A task's text is the current unit of work, not the epic: reference the Trello card shortUrl instead of restating the plan, never mirror task history into the board or vice versa. Finishing a chunk means BOTH: `prescient task ready` for the verdict, and the epic's `## Work items` / `## Log` updated in the repo doc.
- Exact shapes: $HOME/Desktop/personal/repos/prescient/docs/agent-admin.md
