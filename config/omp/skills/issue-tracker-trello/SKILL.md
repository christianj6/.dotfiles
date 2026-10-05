---
name: issue-tracker-trello
description: Trello-backed issue tracker for wayfinder and task triage — the "Development" board. Read before any wayfinding operation or when publishing or fetching tasks on the board.
---

# Issue tracker: Trello (Development board)

Issues, wayfinding maps, and cross-project tasks live on the Trello board **Development**. **Scope: personal development only — system work (dotfiles, omp/herdr tooling) and personal projects. The work space (Tallence: thor, telia, ...) is out of scope and stays in work trackers.** All operations are Trello REST calls with credentials from `~/.dotfiles/.env`. The board is a source of truth agents return to — lightweight checkpoints, not ceremony: structure work against the roadmap, keep every significant piece of dev tracked, never drift into hacking from memory.

```bash
set -a; source ~/.dotfiles/.env; set +a
# then every call:
curl -s -G https://api.trello.com/1/<endpoint> --data-urlencode "key=$TRELLO_KEY" --data-urlencode "token=$TRELLO_TOKEN" <params>
# writes add -X POST or -X PUT and their params the same way
```

Resolve ids by name once per session (cache them):

- Board id: `GET /1/members/me/boards?fields=name` → filter `name == "Development"`.
- List ids: `GET /1/boards/<boardId>/lists?fields=name`.
- Label ids: `GET /1/boards/<boardId>/labels?fields=name`.
- Own member id: `GET /1/members/me?fields=id`.

## Conventions

2026-10-05: live convention on the shared Development board — Frontier renamed to `Messy`, Todo renamed to `Selected for development`; the `Maps` list was DEPRECATED the same day: every project's standing cards migrated into its repo and the (empty) list archived. The board holds tickets only.

- **Board**: `Development`. **Lists** are the pipeline, and there are no standing lists: `Messy` (rough ideas — the entry point), `Selected for development` (scoped, definitely happening), `In Progress` (claimed tickets), `Review` (owner-only gate between In Progress and Done), `Done` (resolved or ruled out). **Per-project work structure, standing context, epics, and wayfinder maps live IN THE REPO** — convention: `docs/DEV_BOARD.md` at the repo root unless the project chose otherwise (e.g. heinzel-exploration: `release/docs/07_DEV_BOARD.md`). Never create context/epic/map cards on the board.
- **Map**: a section of the project's repo doc — NOT a Trello card. Body sections exactly: `## Destination`, `## Notes`, `## Decisions so far`, `## Not yet specified`, `## Out of scope` (semantics as in `skill://wayfinder`). The map resolves its own tickets; the doc's epic `## Log` gets one line at map completion.
- **Ticket**: a card on the board labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`) or `bug`, plus **exactly one project label** — resolved from the repo you are in (repo dir name). No label for it yet → create it yourself (`POST /1/labels?idBoard=<boardId>`, any free color — the name is the identity). Work-scope (Tallence) or ambiguous → stop and ask; never guess. Description starts with `## Question` and the question; a `Blocked by: <card shortUrl>, ...` line sits at the top when blocked. Cross-project card: primary project label plus an `Also: <project>` line.
- **Epic (workstream)**: a section in the project's repo doc per significant chunk of work, with sections: `## Goal` (what done means), `## Design decisions` (durable, agent-facing — summarizes and links repo ADRs like `ADR-0007 (repo)`, never restates them; CONTEXT.md stays in the repo), `## Work items` (index of maps and direct tickets: `- [<name>](<shortUrl>): <status one-liner>` — shortUrls still resolve into board history), `## Log` (dated one-liners: shipped, incidents, recurrences). Every ticket or bug under it names the epic in its description; the doc's Work items index carries the card shortUrl. Chart the epic BEFORE its tickets.
- **When work needs a card** (the baggage line): card it if it touches an existing epic's scope, spans more than one session, adds an abstraction/module/dependency, or changes user-visible behavior. Anything smaller is a drive-by — just work, no card; but the 3rd drive-by in the same subsystem promotes it: create an epic section in the repo doc.
- **Claim** = assign yourself as a member AND move the card to `In Progress` — the session's first write. Unclaimed = no members. `Selected for development` is the scoped staging list: the owner (or a planning session) pulls cards from `Messy` into `Selected for development` once scoped, but claiming itself still lands the card directly in `In Progress`.
- **Blocking** (Trello has no native dependencies): the `Blocked by:` line lists card shortUrls. A ticket is unblocked when every listed card is in `Done`.
- **Resolve**: post the answer as a card comment, move to `Done`, append `- [<ticket name>](<shortUrl>): <one-line gist>` under `## Decisions so far` in the repo doc's map section. Owner review happens via the `Review` list (owner-only gate between `In Progress` and `Done`); agent resolves still go straight to `Done` per this convention.
- **Out of scope**: move the card to `Done`, add a line (gist + why + shortUrl) under `## Out of scope` in the repo doc's map section. A scope boundary is not a step on the route; it never enters Decisions so far.
- **Project context / roadmap**: the repo doc IS the standing context (`docs/DEV_BOARD.md` at the repo root unless the project chose otherwise). Read it when charting a map or choosing tickets; keep it current as roadmap decisions land.
- **Triage labels** (plain task cards, no wayfinder involvement): `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.

## When a skill says "publish to the issue tracker"

Create a card in the right list (see Conventions).

## When a skill says "fetch the relevant ticket"

`GET /1/cards/<shortUrl or id>` plus `GET /1/cards/<id>/actions?filter=commentCard` for history.

## Bootstrap (normally already done; verify before creating anything)

Board `POST /1/boards?name=Development&defaultLists=false&prefs_permissionLevel=private`; lists via `POST /1/lists?idBoard=<boardId>`; labels via `POST /1/labels?idBoard=<boardId>`: `wayfinder:research` (blue), `wayfinder:prototype` (purple), `wayfinder:grilling` (yellow), `wayfinder:task` (orange), `bug` (red), project labels (`prescient` pink, `dotfiles` sky — colors repeat freely, the name is the identity), `needs-triage` (red), `ready-for-agent` (lime), `ready-for-human` (pink), `wontfix` (black). Add a project label the first time a personal project appears — standing context goes straight into the project's repo doc, never onto the board.

## Wayfinding operations

Used by `skill://wayfinder`. The **map** is a section of the project's repo doc (the `Maps` list is archived); tickets are cards on the board.

- **Chart — create the map**: create/extend the map section in the project's repo doc (`docs/DEV_BOARD.md`-style) with the exact body sections; tickets land on the board as below.
- **Create ticket**: `POST /1/cards?idList=<Messy-id>&name=<question as title>&desc=## Question ...`, then labels `wayfinder:<type>` + project. Create-then-wire: all tickets exist before blocking lines reference them.
- **Wire blocking**: `PUT /1/cards/<cardId>?desc=<desc with Blocked by: <shortUrl>, ...>`.
- **Messy query** (formerly Frontier query): `GET /1/lists/<Messy-id>/cards?fields=name,desc,idMembers,shortUrl,idList`; keep cards with empty `idMembers` whose every `Blocked by:` card is in `Done` (check each: `GET /1/cards/<shortUrl>?fields=idList`). First in list order wins. Cards sitting in `Selected for development` are already scoped/selected — not Messy candidates.
- **Claim**: `PUT /1/cards/<cardId>/idMembers?value=<myMemberId>`, then `PUT /1/cards/<cardId>?idList=<In Progress-id>`.
- **Resolve**: `POST /1/cards/<cardId>/actions/comments?text=<answer>`, `PUT /1/cards/<cardId>?idList=<Done-id>`, then edit the repo doc: append the new Decisions-so-far line to the map section. (Owner review via `Review` happens outside this op; the resolve mechanics are unchanged.)
- **Research tickets** fire as parallel subagents; each resolves its own card (claim → work → resolve) so concurrent sessions never touch the same card.

## Bugs and recurrence

A bug tied to tracked work never becomes an isolated card:
1. Check the repo doc's epic `## Work items` for a `bug` card in the same area. Open one → comment (`recurred <date>: <symptom>; suspicion: ...`) + epic `## Log` line. Closed with the same root cause → REOPEN it (move back to `Messy`, add the recurrence comment). One card per recurring issue.
2. No matching card → create in `Messy`, label `bug` + project, name the epic in the description, add the index line to the doc's epic Work items.

Bugs outside any epic: same, minus the epic reference — still project-labelled. Two or more open bug cards in the same subsystem → propose an epic section in the repo doc (hygiene flags this).

## Delegation handoff (board ↔ subagents)

The orchestrator owns ALL board writes; subagents never touch Trello.
- **Down**: a delegation spec for card work must carry the card's context — epic `## Goal` + relevant `## Design decisions`, the ticket's `## Question`, and acceptance criteria (inline for short, `local://` file for long).
- **Up**: when reviewed work lands, the orchestrator updates the board in the same turn: resolve ops, epic `## Work items` line, and distills anything durable into the repo doc's `## Design decisions`. The board is long-term memory for tickets; the repo doc is long-term memory for structure — decisions that live only in a session are lost.
- **Unfinished at session end**: comment a state snapshot (done / next) on the card; it stays `In Progress` as the handoff.

## Scenario → board action

- Significant work starts — or you notice you are working on something the board does not track: stop, create/locate the epic section in the repo doc, create the ticket, then work.
- New personal project surfaces on the board (repo or chat): create its project label immediately and start its repo doc (standing context); mention it, keep going. Work-scope project → refuse and say why.
- Design decision crystallizes (grilling, review): the repo doc's `## Design decisions` updated the same turn.
- Bug or regression: Bugs and recurrence, above.
- Work lands or is abandoned: card moves; epic index and `## Log` updated; nothing leaves the board unrecorded.

## Session checkpoint & hygiene

Starting dev work in a personal project → ONE board GET (`GET /1/boards/<boardId>/cards?fields=name,labels,idList,idMembers`), then:
1. `needs-triage` cards (yours or the human's) → triage first: fold into epics/tickets or report back. Cards the human adds carry this label.
2. Your claimed `In Progress` cards → resume or release (unclaim + snapshot comment). Claims never rot.
3. The project's repo doc (work structure + standing context) → structure the session against it.

After any batch of card creations, hygiene: flag cards with no project label, repo-doc Work items entries pointing at cards no longer in Messy/Selected for development/In Progress/Review/Done, and subsystems with 2+ open bug cards (propose an epic section). Fix before proceeding.

omp injects this checkpoint automatically at session start (`omp-board-checkpoint extension: once per process, with the project's roadmap gist, open epics, and any needs-triage/In Progress cards; skipped only for work-scope cwd). The manual rule above is the fallback — act on what the injection names. Deprecation implication for the extension: ALL per-project Roadmap cards were archived 2026-10-05 when Maps was deprecated — the checkpoint must tolerate a missing Roadmap card for every project and point at the repo work-structure doc instead.

## Parallel sessions

Claims are members-on-cards, so expect concurrent editors. Edit the repo doc like any tracked file (concurrent-agent edits are normal — re-read before editing). Claim before any work.
