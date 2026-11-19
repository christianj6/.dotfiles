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

### Shipped but not live: a fix in a long-running process is not a fix

**Goal.** A committed fix is not reported as done until the process that runs it has
restarted and is observed on the new behaviour. No owner-visible fix may sit silently
inert behind a process that predates it.

**Design decisions.**
- **Four instances in one session is a class, not four accidents.** VERSION sat at 35
  across 52 commits, the Discord bot ran 9 days stale, the lifeview daemon predated its
  own parser, and three omp panes predated the compaction config.
- **The failure is silent by construction.** A long-running process reads its config
  once at start, so a committed change is invisible to it, and every check that reads
  *config* (not process state) reports healthy.
- **Therefore the check must read live process state and name the process.** `workspace-up`
  compares a service's start time against its code's mtime, and now compares each omp
  pane's *logged* `contextWindow`/`thresholdTokens` against the config, naming any that
  disagree with the reason and the remedy ("restart its omp"). The logged value is the
  only evidence of what the running process actually believes.
- **`contextWindow: 0` is worse than a low threshold**: the guard
  `if (window <= 0) return false` short-circuits before any threshold is consulted, so
  neither a percentage nor a token count can apply and the session grows until the
  provider rejects it. That was the 800k+ the owner saw.
- **A health check that cries wolf is worse than none.** The first omp/unhealthy check
  reported the Discord bot as never having logged `bot ready` because it tailed only
  the last 400 log lines; a healthy service named unhealthy trains the owner to ignore
  the whole summary. Checks must satisfy themselves on evidence of live operation, not
  on the absence of an old line in a truncated window.
- **Distinguish "no turn yet" from "stale".** A process started after the config has no
  logged decision; that is not staleness and must not be reported as needing a restart.

**Work items.**
- Compaction: three live panes ran `contextWindow 0` (never compact) or the old 660k —
  `docs/issue-compaction-not-firing.md`.
- `scripts/workspace-up`: omp pane threshold check with reason + remedy.

**Log.**
- 2026-11-18: owner reported compaction "not working", agents at 800k+. Config was
  correct; prescient (23590) and bro (23795) logged `contextWindow 0` from Nov 12 —
  never compacts — and thor (24105) still had 660000. Restarted all three; each now
  logs 1M / 500000.
- 2026-11-18: `workspace-up` names stale omp panes (3fb0111). Caught the coordinator's
  own pane (wD:p9) and ai-assisted-dev (wG:p6); it also false-positived the Discord bot
  as never ready (400-line tail), fixed the same day.
- 2026-11-18: wD:p9 restarted onto pid 41690, same session `01a0ffdb` (13052 entries intact); it auto-compacted
  907K -> 5.7% of 1M on resume — the first proof the setting applies to a live pane.

### Guards that cannot guard: the check reports success while protecting nothing

**Goal.** Every guard verifies the thing it actually holds, not a name for it. A lock, a
claim, or a threshold that can silently stop binding must fail loudly, and its failure
must be visible in a file someone reads.

**Design decisions.**
- **Four instances, one shape: the guard's own success signal is the bug.**
  - `herdr:claude` foreign claim: every `report-agent` returned "ok" and applied none.
  - `contextWindow: 0`: `if (window <= 0) return false` short-circuits before any threshold,
    so compaction was disabled while the config read correctly.
  - `flock` on `/tmp/<plugin>.lock`: macOS unlinks `/tmp` entries, freeing the pathname but
    not the inode; the next launch creates a fresh file, flocks it, and both processes
    believe they are the singleton.
  - the plugin log on `/tmp`: the older daemon wrote to an orphaned inode, so its copies of
    the duplicate opens never appeared in the file the coordinator read.
- **Verify the identity, not the path.** `stat(path)` vs `fstat(fd)` on `(st_dev, st_ino)`
  after acquiring; re-take the path each tick (`keep()`), or exit if another holder has it.
- **State that guards live belongs outside `/tmp`.** Locks and logs go to
  `~/.local/state/herdr/plugins/<plugin-id>/`; the parent is created on demand.
- **A diagnostic log that silently disappears is worse than none**: it makes a partial
  record look complete.
- **One implementation, four consumers.** `config/herdr/plugins/_shared/singleton.py`; no
  plugin keeps its own copy of the lock dance.

**Work items.**
- duplicate auto-tasks (owner-visible: two cards per direct message) —
  `docs/task-fix-duplicate-tasks.md`, `docs/task-shared-singleton-lock.md`.
- `_shared/singleton.py`: shared lock for lifeview-fallback, claude-name, agent-discord,
  omp-watch (46f24e6).

**Log.**
- 2026-11-19: owner: "if i give a message directly to an agent it gets two duplicate tasks".
  Cause: two `lifeview.py --daemon` processes, each holding `/tmp/lifeview-fallback.lock` on
  a different inode (92236289 from Nov 12, 108131618 from Nov 18), both logging the same
  open in the same second. Lock fixed (3a5f8c0): path outside `/tmp`, inode-checked,
  `keep()` each tick.
- 2026-11-19: the same fault was live in agent-discord (lock file **gone**, bot holding an
  orphaned inode — the next `workspace-up` would have started a second bot), claude-name
  (two daemons), omp-watch (latent). Shared module + logs off `/tmp` (46f24e6); counts
  1/1/1/1; bot holds one gateway connection and logged a fresh `bot ready`.
- 2026-11-19: proven live in the bot's own log — `another bridge instance holds the lock --
  exiting` at 14:48:37, then a normal notification at 14:51:04.
- 2026-11-19: 45 duplicate groups found (44 pairs, one triple). Two open pairs await the
  owner's drop; 34 done pairs are left untouched because dropping one would rewrite a
  resolution the owner gave, and 6 have different resolutions (ambiguous). The store
  refuses an agent's drop by design.
