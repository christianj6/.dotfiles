# .dotfiles dev board

Migrated 2026-10-05 from the Trello Development board `Maps` list (card
`Roadmap — .dotfiles`, https://trello.com/c/LGb432eM, archived with a
migration comment); the board holds tickets only (Messy | Selected for
development | In Progress | Review | Done). Board conventions:
`config/omp/skills/issue-tracker-trello/SKILL.md`.

## Standing context

Standing context for the ~/.dotfiles repo (omp/herdr harness tooling).
Created by HarnessFixScout checkpoint 2026-10-01 ("body to be filled by
orchestrator" — filled at migration time):

- This repo versions the omp/herdr harness setup: omp extensions and
  skills (`config/omp/`), herdr config/plugins/skills (`config/herdr/`),
  the shell/nvim/terminal dotfiles, and `setup.sh` as the idempotent
  installer for a fresh machine.
- Standing work conventions live in `config/omp/skills/` — notably
  `issue-tracker-trello` (board conventions) and `herdr-workstreams`
  (pane/peer workflows; `omp-peer` is the default agent-to-agent comm
  helper).
- Board tickets for this repo carry the `dotfiles` project label; this
  project has no Maps cards anymore — work structure lives here.

## Epics

### Life view: agent icons tell the truth

**Goal.** An agent's icon means what it says: amber while it works, green when
there is work for the owner to look at, grey only when nothing is open. The same
for every project, whether or not it runs a Claude.

**Design decisions.**
- The ring comes from the hub, not from a local rank table: the plugin asks
  prescient's `/api/tasks/status` and refuses a rank-table version it does not
  know (`prescient/tasks/status.py`, `docs/design-task-hub.md`).
- **Readiness is a property of the project, not of an agent.** Hub items carry
  `agent: null` and a *role* dest, so any agent-keyed matching is empty by
  construction. Match on `project` + `target`.
- **A project settles on its omp** — the owner always runs one, Claude is an
  optional workhorse. Read the Claude's transcript when it exists (better
  evidence), the omp's when not. Never require a Claude.
- **Only states the harness can drive count as candidates.** `created`/`parked`/
  `undelivered` have no harness route to `ready`; counting them made two
  candidates = "ambiguous" = green never happens.
- **An unknown tier or state renders conservatively**, never as healthy.

**Work items.**
- prescient `status()` ranks every open item of a project, whichever target
  (`f8e0c45`) — the amber-vs-green asymmetry.
- life view `auto_ready` project-keyed, hub-state predicate, omp settler
  (`4609707`, plus my fixes `22fc777`).
- Four breaks diagnosed and recorded: `docs/auto-ready-four-breaks.md`,
  `docs/status-asymmetry-root-cause.md`.

**Log.**
- 2026-11-03: owner reported prescient going green while other projects went
  amber→grey. Two independent bugs found (one-per-role ranking; agent-keyed
  auto-ready), plus a third and fourth on the way. Fixed; the ready invariant
  now holds across all five projects.
- 2026-11-03: `--explain` contradicted the icon (old agent-keyed selector beside
  a project-keyed one). Fixed — the diagnostic must not disagree with the thing
  it explains.

### Harness delivery and privacy guardrails

**Goal.** An agent-to-agent message either lands or says plainly that it did
not; nothing private reaches the public dotfiles repo.

**Design decisions.**
- **Never trust a terminal box as proof of submission.** The box is evidence
  only when the box is actually seen; otherwise `None` (no blind Enter), never
  `False`.
- **A guess is never recorded as an actor.** An unattributed task mutation is
  refused; a review gate refuses automatic actors. The gate refuses *machines*,
  not a person who types a name — so the protection is discipline, not a check
  (`docs/hardening-anonymous-drop-attribution.md`).
- **Three local guard layers, no CI**: `pre-commit`, `commit-msg`, `pre-push`,
  each auditing what git actually commits and pushes; plus `scripts/git-guard.py`
  blocking `--no-verify` and `core.hooksPath` overrides for omp and Claude.

**Work items.**
- nested-REPL delivery fixed (`698c8b3`): nudges into an nvim-nested omp pane
  no longer need a human Enter — `docs/bug-nested-repl-delivery.md`.
- privacy guard push-time hole closed (`b62443f`): `--pre-push` audits every
  commit a push publishes — `docs/privacy-guardrail-audit.md`.
- actor provenance refused when absent (`f9c305f`) — `docs/hardening-anonymous-drop-attribution.md`.

**Log.**
- 2026-11-03: audit found the extension audited staged content for BOTH commit
  and push, so `--no-verify` + push published unchecked. Reproduced, fixed,
  verified with a mid-history leak.
- 2026-11-03: a mid-history leak (committed then deleted) is caught — the guard
  reads every commit in the push, not the tip.

### Review discipline

**Goal.** A "fixed" claim is about a system, not a function.

**Design decisions.** `rule://fixed-claim-call-sites` — name the call sites,
grep for the rule rather than the name, check the thing that *runs* (binary,
served page, microphone), and write the proving test at the shape that broke.
Three of the day's defects shared the shape "function verified, system
inferred", plus a fourth where absence of a name was read as absence of a
behaviour.

**Log.** 2026-11-03: rule written after the third instance, extended the same
day by my own gap-3 error.

### Provenance: whose words started this

**Goal.** Work is tracked wherever it comes from — the owner typing, bro, a
coordinator's dispatch — and the harness can tell the owner's requests from agent
comms without guessing.

**Design decisions.**
- **The sender is written into the message, not inferred from it.** A pane delivery
  is `{content, role}` with no sender, so provenance is recorded at delivery:
  `[from:<role> project:<p> id:<name>]` (`docs/design-message-tags.md`). `omp-peer`
  adds it; prescient's `_deliver` adds it.
- **`[from:owner]` beats every shape rule** — the owner's words can look like anything.
- **`[from:hamess]`/`[from:coordinator]`/`[from:worker]` never card.** Agent-to-agent
  messages are comms by definition; that is what stopped the echo.
- **Only harness wrappers may precede a tag.** Wrap-strip then anchor, so a tag pasted
  mid-text never re-attributes a message (`docs/issue-tag-line-two.md`).
- **A shape classifier is the fallback, not the rule**, and an unrecognised
  `prescient:` line is reported rather than swallowed silently.

**Work items.**
- `omp-peer` tags every relay; the plugin parses tag → machinery shapes → owner.
- auto-task is per-agent by role (omp coordinates, Claude is the workhorse); coverage
  is project-keyed (`covering_items`) — the agent-keyed check kept the echo alive.
- `prescient project status --project|--all`: a peer's status is a command, not a turn
  (no model).

**Log.**
- 2026-11-06 → 11-09: the echo had **four** independent causes (agent-keyed coverage, a
  daemon older than the parser, an anchored tag, a wrapper on its own line). Each alone
  reproduced it; that is why fixing them one at a time kept it alive.
- 2026-11-09: verified the nudge/tweak literals are all machinery and the loop is not
  reproducing; five literal regression tests added.

### Harness versioning and rollout

**Goal.** One glance tells the owner every pane is on the current instructions.

**Design decisions.**
- **`config/omp/VERSION` is the single number for the whole harness** — omp and claude
  panes both report it, so the columns are comparable.
- **A version is read, never guessed.** omp writes its marker at extension load; claude
  writes one at SessionStart. No marker → `-`, not an approximation.
- **The claude pane name carries the harness version**, not the CLI's major; the CLI
  version is demoted to a note.
- **Rollout keys on VERSION**, so a stale VERSION silently rolls nothing — the bump is
  part of shipping an instruction change, not an afterthought.

**Log.**
- 2026-11-09: VERSION sat at 35 across 52 commits; the dry run said `up-to-date` for
  every pane and would have restarted none. Bumped to 36 and rolled everything.
- 2026-11-09: claude panes went from `claude-v2-wdpa` (CLI major) to `v36` read from a
  marker, matching the omp panes.
