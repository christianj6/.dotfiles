---
name: herdr-workstreams
description: Start, find, and clean up herdr workstreams — new workspaces ("spaces"), tabs, panes, and git worktrees — spin up claude/omp subagent panes that auto-register in herdr, and message other agents (send instructions, get replies) — when the user asks to spin up a workstream/space/worktree/tab/pane, or to tell/instruct/have another agent do something. Companion to the herdr skill. Requires HERDR_ENV=1.
---

# Herdr workstreams

Recipes for starting new work in herdr. Every creation command returns JSON on
stdout — read IDs from the response, never invent them. Creation defaults to
NOT touching the user's focus; keep it that way (`--no-focus`). This skill
overrides the upstream herdr skill's "do not create a workspace ... unless the
user explicitly requests that topology": in these trigger cases the requested
topology IS the workstream.

## Create

New workstream on a git repo — new branch + isolated checkout + workspace +
tab + root pane in ONE call:

    herdr worktree create --cwd "$PWD" --branch <branch-name> --label <short-name> --no-focus

Result: `result.workspace.workspace_id`, `result.tab.tab_id`,
`result.root_pane.pane_id`. The root pane starts in the worktree checkout
(`~/.herdr/worktrees/<repo>/<branch-slug>`). Requires a git repo.

New space without a new branch (non-git directory, or same repo + branch):

    herdr workspace create --cwd "$PWD" --label <short-name> --no-focus

Same result shape; root pane starts at `--cwd`.

New tab in an EXISTING workspace (fresh root pane, no new space):

    herdr tab create --workspace <workspace_id> --no-focus

Result: `result.tab.tab_id`, `result.root_pane.pane_id`. Omitting `--cwd`
uses the configured default for new panes (this setup: clean shell in
`$HOME`); pass `--cwd` to start elsewhere. Name the tab for the user:
`--label TEXT` at create, or `herdr tab rename <tab_id> <label>` after.

Extra pane in the CURRENT tab (quick side shell, no new space):

    herdr pane split --current --direction right --cwd "$PWD" --no-focus

Result: `result.pane.pane_id`. Use `--direction down` for tall/narrow panes.

## After creation

- Report the workspace and pane IDs back to the user.
- The root pane is a plain shell. To put an agent in it, use the subagent
  recipe below (NOT `herdr agent start` on a project-dir pane -- that
  fails, see why there). A standalone `omp` pane does not auto-resume
  after a herdr server restart in this setup
  (`resume_agents_on_restore = false`); the user's main omp normally runs
  inside nvim (ctrl-a REPL).
- To jump the user's view there anyway: `herdr workspace focus <id>` — only on
  explicit request.

## Subagents: you are main, claude/omp panes are the workers

In this workspace the omp session you are running IS the project's main
agent: it owns the conversation, the repo context, and the herdr driving.
Other agents are spun up on demand as SIBLING PANES -- never inside your
own pane -- and they register themselves in herdr's sidebar when started
this way. Verified live 2026-09-15 for claude (`w6:pM | claude | idle`)
and the same shape works for a second omp.

1. **Split a sibling pane WITHOUT `--cwd`:**

       herdr pane split --current --direction right --no-focus

   Omitting `--cwd` is load-bearing: `[terminal] new_cwd = "home"` gives a
   clean zsh in `$HOME`. A pane created directly in a project dir
   auto-starts nvim from the shell config, so its foreground process is
   nvim and every agent-start path rejects it with `agent_pane_busy`.

2. **Push the agent in as a command** -- this is what makes it the pane's
   FOREGROUND process, which is the only thing herdr's screen detection
   reads:

       herdr pane run <pane_id> "cd /path/to/project && claude"
       herdr pane run <pane_id> "cd /path/to/project && omp"

3. **Verify** (allow a few seconds; a first run in an untrusted directory
   sits on claude's trust prompt, which herdr reports as `blocked`):

       herdr agent list        # pane_id | agent | agent_status

4. **Name it, then talk to it** with the peer-comms recipes below:

       herdr agent rename <pane_id> <name>
       omp-peer send <name> "<instruction>" --wait-reply

5. **Close the pane you created when the work is done** (`herdr pane close
   <pane_id>`) -- that ends the agent with it.

`herdr agent start <name> --kind <kind> --pane <id>` is the "official"
path but only accepts a pane already sitting at an interactive prompt and
never creates layout, so in practice it works only on a freshly split
`$HOME` pane. `pane run` is preferred: it works whether the pane needs a
`cd` first or not.

### Never run another agent inside your own pane

herdr attributes exactly one agent per pane and reads only that pane's
foreground process. An agent started inside your pane (a `claude` in an
nvim `:terminal`, or anything under the ctrl-a REPL split) is therefore
INVISIBLE to the sidebar -- and worse, claude's SessionStart hook plants a
`herdr:claude` agent_session claim on YOUR pane. That claim takes
authority: herdr keeps accepting the omp watcher's state reports with
"ok" while applying none, so your own pane's status freezes at whatever it
was (hit live twice on 2026-09-15). Recovery needs the pane recreated or
`scripts/herdr-clear-agent-claims.sh` with the server stopped; nothing the
watcher can send wins.

If you only need a one-shot probe of another agent CLI, strip the herdr
env so no claim is planted:

    env -u HERDR_ENV -u HERDR_PANE_ID -u HERDR_SOCKET_PATH claude -p "..."

## Peer comms (agent-to-agent)

Every agent in a herdr pane can message every other one: the herdr CLI is on
every pane's PATH and `HERDR_ENV=1` reaches agents through the env chain.
The address book is `herdr agent list` (names + pane ids). Give every agent
you start a name (`agent start` takes one); adopt an existing unnamed one
with `herdr agent rename <pane_id> <name>`.

Send with the `omp-peer` helper (on PATH), NOT `agent prompt --wait`:
omp lifecycle state reaches herdr via a ~3s transcript poller, so fast turns
finish between polls and `--wait` false-stalls (`agent_prompt_stalled`) even
on success. omp-peer fires the prompt and confirms against the peer's own
transcript instead:

    omp-peer send <name-or-pane> "<instruction>"                # fires + confirms delivery
    omp-peer send <name-or-pane> "<instruction>" --wait-reply   # then prints the peer's reply text

- Big context goes by file: write it, then send "read /path/x.md and ..."
  — keep the typed prompt tiny.
- Read a peer's screen directly: `herdr agent read <target> --source recent-unwrapped`.
- Replies to delegated tasks arrive in the peer's own turn (you poll with
  `--wait-reply`); PUSH only proactive events (blocked, done, needs-input).
  The peer can push back the same way — `omp-peer send <your-name> ...` —
  and a prompt landing mid-turn just queues, like the user typing.
- No reply within ~90s of a confirmed delivery usually means the peer is
  stuck on an approval dialog (omp approvals are UI-only, invisible to
  herdr): STOP and surface it to the user instead of resending.
- REPL-nested peers are guarded automatically: omp-peer checks the peer's
  input box is visible and toggles it open (ctrl+a, the user's yarepl
  binding) if not — refusing rather than typing blind after two attempts.
  Pass `--no-guard` for standalone agent panes.
- NEVER let a nested agent CLI claim your pane. A `claude`/`codex` process
  you spawn as a subprocess inherits `HERDR_PANE_ID` and registers ITSELF
  as that pane's agent session -- even a one-shot `claude -p` probe. herdr
  then accepts every later report for the pane with "ok" and applies none,
  so the pane's sidebar status freezes permanently (the claim is persisted
  in `~/.config/herdr/session.json`; release-agent cannot undo it; only
  recreating the pane or `scripts/herdr-clear-agent-claims.sh` clears it).
  Strip the env when probing another agent CLI:
      env -u HERDR_ENV -u HERDR_PANE_ID -u HERDR_SOCKET_PATH claude -p "..."
  Real sessions of another agent belong in their OWN pane, never inside a
  pane that already hosts one.
- The user has right of way: their keystrokes land in the same input box.
  Never prompt a peer the user is actively typing into.

## Find and verify

    herdr workspace list
    herdr workspace get <workspace_id>
    herdr worktree list
    herdr pane list --workspace <workspace_id>
    herdr tab list --workspace <workspace_id>

## Clean up

Only workstreams you or the user created via these recipes:

    herdr worktree remove --workspace <workspace_id> --force   # removes the git worktree AND closes the workspace
    herdr workspace close <workspace_id>                       # workspace-only spaces
    herdr tab close <tab_id>                                   # plain tabs

Never close workspaces, tabs, or panes you did not create.
