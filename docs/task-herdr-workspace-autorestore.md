# TASK: restore the owner's workspace shape automatically after a herdr restart

Owner: *"get all of the workspaces into the state i like (nvim+omp on the left, claude on the
right) and then after that is done see if you can get your claude to figure out how to make
this more 'automatic' ie if i just run herdr after a restart i easily get back into the
workspaces the way i like them (wo overriding any config that prevents me from using herdr
normally eg to open a new pane and freely access the terminal)"*

## The target state, per project tab

```
┌────────────────┬────────────────┐
│ nvim + omp     │ claude         │
│ (yarepl ctrl+a)│ (the workhorse)│
└────────────────┴────────────────┘
```

After this morning's reboot, all ten panes existed but were **empty** — no nvim, no omp, no
claude. Current state after my manual pass: 9 of 10 restored, `wD:pH` (the dotfiles right-hand
pane) still needs Claude.

## Facts established by experiment (do not re-derive)

1. **A new pane starts `nvim` as its root process.** `herdr pane process-info` shows
   `foreground_processes: [nvim]` and `shell_pid` **equal to nvim's pid**. Consequence:
   quitting nvim ends the pane — `:qa` made the pane disappear (`pane_not_found` after).
2. **`herdr pane run <pane> <cmd>` types into the running process**, it does not exec. Sending
   `claude` to an nvim pane pasted it into nvim's buffer (visible error:
   `Vim:E21: Cannot make changes, 'modifiable' is off`).
3. **A working claude pane** (`wD:p6`) has `foreground_processes: [claude]` and a *different*
   `shell_pid` (14294) — so in that pane `claude` replaced the shell, or the pane was created
   with a command.
4. `config/herdr/config.toml` has `new_cwd = "home"` under `[terminal]` and **no**
   `default_shell`; herdr's documented default is `$SHELL`. Yet new panes get nvim — so
   something else supplies it (saved layout? a session/restore file? a herdr setting not in the
   file?). **Find the actual mechanism and cite it.**
5. `resume_agents_on_restore = false` is deliberate (with it on, herdr relaunches
   `omp --resume` and clobbers nvim — observed 2026-09-02). **Do not turn it on.**
6. `herdr pane send-keys <pane> colon` enters nvim COMMAND mode; `send-text ":"` does not.
   In the yarepl float, keys go to the **REPL**, not nvim — toggle `ctrl+a` first.

## What to build

**A. A restore command** — `scripts/herdr-restore` (or extend `workspace-rollout`) that brings
every tab to the target shape:

- for each project tab, if the left pane has no omp: start nvim, then `ctrl+a` to open the
  REPL (verified working for 6 panes today);
- if the right pane does not exist: create it **as a claude pane**, not an nvim pane;
- if the right pane exists but has no claude: start claude in it;
- **idempotent**: run it twice, nothing changes the second time;
- prints one line per pane: `wD:p7  omp  ok` / `wD:pH  claude  started`.

**B. Make it automatic on `herdr` start** *without* breaking normal herdr use.

The owner's constraint is explicit: do not override config that stops him opening a new pane
or using the terminal normally. So:

- prefer a herdr **`[[startup]]`** plugin hook (the pattern `agent-discord`, `claude-name` and
  `lifeview-fallback` already use) that runs the restore once per server start;
- it must **never** change `[terminal]` defaults, keybindings, or `resume_agents_on_restore`;
- it must be safe to run when everything is already up (idempotent), and must not fight the
  owner if he has deliberately closed a pane — record a per-tab "owner closed this" marker, or
  only restore panes that exist but are empty, and say which choice you made.

**C. Answer the mechanism question in the report.** Where does a new pane's `nvim` come from?
That decides whether B is a hook or a layout setting, and I could not find it by inspection.

## Acceptance

1. `wD:pH` (or whatever the dotfiles right pane is) runs **claude**, and the dotfiles tab has
   nvim+omp left, claude right.
2. Every other project tab matches the target shape; paste `herdr pane list` and the
   `process-info` fg for one omp pane and one claude pane.
3. The restore script is idempotent — show a second run making no changes.
4. It runs automatically on server start via the mechanism you found, with the herdr config
   untouched: diff `config/herdr/config.toml` to prove no behavioural setting changed.
5. Opening a new pane by hand still gives the owner a normal terminal/nvim, and the terminal is
   reachable — demonstrate it.
6. The report cites the source of the `nvim` default (fact 4).

## Rules
- Do not turn on `resume_agents_on_restore`.
- Do not add keybindings that shadow normal herdr use.
- The owner is in `wD:p9` right now — **never touch that pane**, and prefer `ctrl+a`/`send-keys`
  over anything that quits nvim, since quitting kills the pane.
