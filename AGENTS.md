# Agent rules for this repo

This repo is **PUBLIC** (github.com/christianj6/.dotfiles): anyone can clone
it, and fresh-VM setup works without authentication. Everything pushed is
published.

## Hard rule — no private content

Never stage or commit:

- **Credential values** (API keys, tokens, passwords, private keys). Secrets
  live in `~/.dotfiles/.env`, which is gitignored. Referencing env-var
  *names* in code and docs is fine.
- **Home-anchored private paths** — anything under the owner's Desktop
  (personal projects, work workspace checkout locations). Bare scope
  markers in scope-rule code (e.g. a work-marker constant) are fine.
- **Personal project content**: planning notes, task bodies, board card
  exports, session/transcript files, chat logs — even paraphrased or
  excerpted. These live in private repos and in the owner's head, not here.

Fine to publish (owner decision 2026-10-05): project names, one-line board
bookkeeping, migration status, epic titles — this only reproduces at a high
level what is visible in the code base and auditable from commit history.

## Enforcement

Local layers only, against `scripts/private-patterns.txt` (the owner's
tuning knob) — deliberately no cloud CI for this (owner decision
2026-10-05, too much infrastructure for a simple local check):

1. Git hooks (`setup.sh` sets `core.hooksPath=.githooks`), all running
   `scripts/check-private.py`:
   - `pre-commit` — the staged content, read from the index;
   - `commit-msg` — the commit message (messages are published too);
   - `pre-push` — every commit the push publishes, content and messages,
     however it was committed.
2. `scripts/git-guard.py` — keeps agents from switching the hooks off:
   blocks `--no-verify` (and commit's `-n`), `core.hooksPath` overrides,
   and commits from a clone whose hooks aren't wired. Used by omp
   (`config/omp/extensions/omp-privacy-guard.ts`) and Claude (the
   `PreToolUse` Bash hook in `config/claude/settings.json`). It reads the
   command line, so a script that runs git is out of its sight; the hooks
   still run there.

Manual full-tree audit when wanted: `python3 scripts/check-private.py --all`.

If a line is flagged but genuinely belongs in the repo, propose a pattern
change to the owner — never bypass the hook or the guard. If you find
private content already tracked, STOP and surface it to the owner instead
of committing around it.

## On-demand MCP servers

MCP servers are NOT registered globally (a global entry leaks into every
pane, including omp panes that import claude's config). Owner decision
2026-10-06: register per-project, on request only. Current on-demand
server: `rea` (decomp tasks) — when the owner asks for decomp work in a
project, register it there for the claude pane with:

    claude mcp add rea -s project -- npx -y rea-agents@6.7.0 mcp

Remove it the same way (`claude mcp remove rea -s project`) when the work
is done. Never re-add user-scope MCP servers.

## Working with your omp coordinator (file-only handoff)

For claude panes; omp's side of this lives in its system prompt.

1. **Specs arrive in a file.** Read the whole file before starting; do no speculative work first.
2. **Pane messages are the path + one line.** Never paste a spec or report body into a pane.
3. **Write your report to a file** next to the spec: what changed, what was run, results. Say so there if you edited anything outside the spec.
4. **Send the path back** with `omp-peer send <omp-name> "<path + one line>"`. The address book is `herdr agent list`.
5. **One task at a time.**

Messaging another project's claude pane is off-limits; route it through omp
(`rule://coordinator-network`). Details: `docs/handoff-verification.md`.

## Agent-to-agent messages: always through `omp-peer send`

**Never type into another agent's pane by hand** — no bare `herdr agent
prompt`, `herdr pane send-text` or `tmux send-keys` to another agent.
`omp-peer send <name> "<path + one line>"` puts the sender's tag on the
first line (`[from:<role> project:<project> id:<name>]`, see
`docs/design-message-tags.md`), and it confirms delivery on omp and claude
targets alike.

A pane transcript records no sender (every entry is role "user"), so the
life view's harness reads that tag to tell the owner's requests from agent
comms. An untagged message falls back to guessing from its wording, which
records agent dispatches as the owner's. `--from owner` is for relaying
the owner's own words by hand. Text that already starts with `[from:` is
sent unchanged.

## Config model roles: never commit the churn

The owner switches the `modelRoles:` values in `config/omp/config.yml`
frequently (task/advisor/smol/slow). Those hunks stay UNCOMMITTED by
policy (owner decision 2026-10-26) — commit only structural config.yml
changes (extensions, keys, wiring), and re-check `git diff` before any
config.yml commit so model-role churn is never swept in.
