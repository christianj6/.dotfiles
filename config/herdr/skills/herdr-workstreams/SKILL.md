---
name: herdr-workstreams
description: Start, find, and clean up herdr workstreams — new workspaces ("spaces"), tabs, panes, and git worktrees — and message other agents (send instructions, get replies) — when the user asks to spin up a workstream/space/worktree/tab/pane, or to tell/instruct/have another agent do something. Companion to the herdr skill. Requires HERDR_ENV=1.
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
- The root pane is a plain shell. Start an agent in it only if the user asked
  for one (kind list: `herdr agent`):
      herdr agent start <name> --kind claude --pane <pane_id>
  Note: a standalone `omp` pane does not auto-resume after a herdr server
  restart in this setup (`resume_agents_on_restore = false`); the user's omp
  normally runs inside nvim (ctrl-a REPL).
- To jump the user's view there anyway: `herdr workspace focus <id>` — only on
  explicit request.

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
