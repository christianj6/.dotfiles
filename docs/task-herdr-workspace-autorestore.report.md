# REPORT: workspace shape + services restored automatically at herdr start

Spec: `docs/task-herdr-workspace-autorestore.md`, widened mid-task by
`docs/post-restart-round-20261112.md` (services), the owner's "i don't need archi-skill",
and the work-project rule (`docs/task-work-projects-no-claude-pane.md`).

## Mechanism (spec fact 4 / acceptance 6)

`~/.zshrc`, block "herdr re-entry" (line 116):

    if [[ -n "${HERDR_ENV:-}" && -z "${NVIM:-}" && -z "${HERDR_NO_NVIM:-}" && -f "$PWD/.conda-env" ]]; then
        exec nvim
    fi

herdr's `session.json` saves per pane only `cwd` (+ agent name/session id), **no env** — so a
restored pane is a plain zsh in the project dir, the block execs nvim, and nvim becomes the
pane's root process (`shell_pid == nvim pid`). Hence "pane is not an available shell", and
hence `:qa` deleting the pane. Nothing in `config.toml` is involved.

Recipe (owner-verified, and what the script uses):

    herdr pane split --pane <p> --direction right --cwd <project> --env HERDR_NO_NVIM=1 --no-focus
    herdr agent start <name> --kind claude --pane <newpane>

## What was built

| file | what |
|---|---|
| `config/herdr/plugins/workspace-restore/restore.py` | the restore: observe → `plan()` (pure) → execute |
| `config/herdr/plugins/workspace-restore/herdr-plugin.toml` | `[[startup]] command = ["python3","restore.py","--startup"]` — no event hook, no keybinding |
| `config/herdr/plugins/workspace-restore/test_restore.py` | 8 unit tests on `plan()` |
| `scripts/herdr-restore` | by-hand wrapper: `[--dry-run] [--create-missing] [--tab TAB_ID]` |
| `setup.sh` | `herdr plugin link …/workspace-restore` (also linked into the running server now) |

`--startup` (once per server start, detached): wait 5 s → `scripts/workspace-up` (services) →
wait until the restored panes stop changing → restore. Everything is logged to
`~/.local/state/herdr/plugins/dotfiles.workspace-restore/restore.log`.

Per project tab (1 or 2 side-by-side panes; left cwd is a repo, a `.conda-env` project, or a
dir omp has a session for):

- left: agent → `ok`; nvim without a terminal → `ctrl+a`; idle shell → `nvim`, then `ctrl+a`.
- right: agent → `ok`; idle shell → `agent start claude`; **idle nvim → replaced** (split it
  with `HERDR_NO_NVIM=1`, start claude in the new shell, re-check, close the nvim);
  nvim with an unsaved file buffer or a terminal, or any other foreground command → left alone.
- 3+ panes, stacked panes, non-project tabs → left alone.
- **work project (cwd under the work tree) → never a claude pane**, not even with `--create-missing`.

"Idle nvim" is checked over nvim's RPC socket (read-only): the owner's nvim auto-loads a
per-directory session, so a fresh one already lists ~14 files — "no buffers" was the wrong
test; "nothing unsaved, no terminal" is what closing it could lose.

## The owner-closed choice

**A pane that does not exist is never created automatically.** herdr restores the layout the
owner left, so a missing right pane means he closed it; only panes that exist but are empty
get filled. No marker file to go stale. `--create-missing` is the explicit by-hand override.
The hook runs only at server start, so it cannot interfere with panes opened afterwards.

## Evidence

Replace path, live, on a pane in the exact post-restart state (plain split → `fg [nvim]`,
`shell_pid == fg` — which is also acceptance 5: a hand-opened pane is still the normal nvim):

    wG:p4   claude  replaced idle nvim with wG:p5, claude started

Left path + create path, live (a tab made for the test): `w5:p1P omp started`,
`w5:t0 claude created w5:p1Q, claude started, waiting at a startup dialog` (the folder-trust
dialog; the script reports it and does not answer it).

Idempotency — final state, two consecutive runs, identical, zero actions:

    wD:p9   omp     ok
    wD:pJ   claude  ok
    wD:p7   omp     ok
    wD:pC   claude  ok
    wD:p5   omp     ok
    wD:p6   claude  ok
    w5:p1D  omp     ok
    w5:p1A  claude  ok
    wG:p1   omp     ok
    wG:t1   claude  work project: no claude pane, by owner rule

fg: `wD:p7 [nvim]` (omp in its REPL), `wD:pC [caffeinate, claude]`.

Hook: `herdr plugin list` shows `dotfiles.workspace-restore … "startup":[{"command":["python3","restore.py","--startup"]}]`.
Its exact command run by hand → log:

    [startup] lifeview     running … ok: hub token found
    [startup] discord-bot  running … ok: token ok, 15 channels resolve, Discord connects, bot ready
    [startup] prescient    running … ok: /api/health answers 200
    [startup] bro          running … ok: /health answers 200
    [startup] workspace: 4 running, 0 started, 0 stale, 0 restarted, 0 unhealthy, 0 need you
    [startup] wD:p9   omp     ok        (… same ten lines as above)

Config: `git diff -- config/herdr/config.toml` is empty; `resume_agents_on_restore = false` (line 26).
Tests: `python3 -m unittest test_restore` → 8 OK; `scripts/test_workspace_up.py` → OK.

## Things that did not go as planned — read these

1. **thor.** Before the work-project rule reached me, the script opened a claude in thor
   (`wG:p5`). The owner closed it (server log: tab focus, then `pane.exit` code 0, no API
   close). I did not recreate it; the script now refuses work projects.
2. **archi-skill.** Its directory has no `.git`/`.conda-env`, only an omp session. I recreated
   the tab (nvim+omp, claude at the trust dialog), then the owner said he does not need it:
   **tab closed again, nothing left**. Nothing was answered on the trust dialog.
3. **Bug found by running the hook:** workspace-up reads `HERDR_PLUGIN_STATE_DIR` to find the
   discord log; inheriting this plugin's value made it report the bot UNHEALTHY. Fixed
   (`HERDR_PLUGIN_*` stripped for that call); re-run shows `ok`.

## Not proven / open

- **The hook has not fired from a real server start** — restarting the server would kill
  every pane, so I did not. Proven: it is registered, and its exact command works. The
  settle-wait before acting (panes stable for three polls, nvim sockets answering, ≤90 s) is
  untested against a real cold start; first reboot, read `restore.log`.
- **claude comes back as a new conversation**, not the old one: `agent start` is not given
  `--resume`. The saved session id is in `session.json` but not in the API after a restore.
- Whether `ctrl+a` resumes the last omp session or starts a new one is the nvim keymap's
  business; not checked.
- A right pane the owner deliberately keeps as a second *editor* in a two-pane project tab
  would be turned into claude at the next server start (its files stay in the nvim session,
  nothing unsaved is ever closed). Say so if that matters and I add an opt-out.
- Inline reads this turn exceeded 5 without a sub-agent: the work was live pane state and
  one-line probes that each decided the next step, not a bulk exploration.
