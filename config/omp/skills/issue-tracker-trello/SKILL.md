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

- **Board**: `Development`. **Lists** are the pipeline: `Maps` (standing cards: wayfinding maps, epics, per-project context), `Frontier` (ready, unclaimed tickets), `In Progress` (claimed tickets), `Done` (resolved or ruled out).
- **Map**: a card in `Maps` labelled `wayfinder:map`. Its description IS the map body, sections exactly: `## Destination`, `## Notes`, `## Decisions so far`, `## Not yet specified`, `## Out of scope` (semantics as in `skill://wayfinder`). A map spawned under an epic carries an `Epic: <shortUrl>` line; the epic indexes the map with one `## Work items` line — the map resolves its own tickets, and the epic `## Log` gets one line at map completion.
- **Ticket**: a card on the same board labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`) or `bug`, plus **exactly one project label** — resolved from the repo you are in (repo dir name). No label for it yet → create it yourself (`POST /1/labels?idBoard=<boardId>`, any free color — the name is the identity) plus the `Roadmap — <project>` context card, and say so once. Work-scope (Tallence) or ambiguous → stop and ask; never guess. Description starts with `## Question` and the question; a `Blocked by: <card shortUrl>, ...` line sits at the top when blocked, and an `Epic: <epic shortUrl>` line when it belongs to a workstream. Cross-project card: primary project label plus an `Also: <project>` line.
- **Epic (workstream)**: one long-lived card in `Maps` per significant chunk of work (e.g. `Mesh Rendering — prescient`), labelled `epic` + project. Description sections: `## Goal` (what done means), `## Design decisions` (durable, agent-facing — summarizes and links repo ADRs like `ADR-0007 (repo)`, never restates them; CONTEXT.md stays in the repo), `## Work items` (index of maps and direct tickets: `- [<name>](<shortUrl>): <status one-liner>`), `## Log` (dated one-liners: shipped, incidents, recurrences). Every ticket or bug under it carries the `Epic:` line and an index entry. Create the epic BEFORE its tickets.
- **When work needs a card** (the baggage line): card it if it touches an existing epic's scope, spans more than one session, adds an abstraction/module/dependency, or changes user-visible behavior. Anything smaller is a drive-by — just work, no card; but the 3rd drive-by in the same subsystem promotes it: create the epic.
- **Claim** = assign yourself as a member AND move the card to `In Progress` — the session's first write. Unclaimed = no members.
- **Blocking** (Trello has no native dependencies): the `Blocked by:` line lists card shortUrls. A ticket is unblocked when every listed card is in `Done`.
- **Resolve**: post the answer as a card comment, move to `Done`, append `- [<ticket name>](<shortUrl>): <one-line gist>` under `## Decisions so far` on the map.
- **Out of scope**: move the card to `Done`, add a line (gist + why + shortUrl) under `## Out of scope` on the map. A scope boundary is not a step on the route; it never enters Decisions so far.
- **Project context / roadmap**: one card per project in `Maps` labelled `context` (`Roadmap — <project>`): standing product context. Read the relevant ones when charting a map or choosing tickets; keep them current as roadmap decisions land.
- **Triage labels** (plain task cards, no wayfinder involvement): `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.

## When a skill says "publish to the issue tracker"

Create a card in the right list (see Conventions).

## When a skill says "fetch the relevant ticket"

`GET /1/cards/<shortUrl or id>` plus `GET /1/cards/<id>/actions?filter=commentCard` for history.

## Bootstrap (normally already done; verify before creating anything)

Board `POST /1/boards?name=Development&defaultLists=false&prefs_permissionLevel=private`; lists via `POST /1/lists?idBoard=<boardId>`; labels via `POST /1/labels?idBoard=<boardId>`: `wayfinder:map` (green), `wayfinder:research` (blue), `wayfinder:prototype` (purple), `wayfinder:grilling` (yellow), `wayfinder:task` (orange), `context` (sky), `epic` (green), `bug` (red), project labels (`prescient` pink, `dotfiles` sky — colors repeat freely, the name is the identity), `needs-triage` (red), `ready-for-agent` (lime), `ready-for-human` (pink), `wontfix` (black). Add a project label + `Roadmap — <project>` context card the first time a personal project appears.

## Wayfinding operations

Used by `skill://wayfinder`. The **map** is a card in `Maps`; tickets are cards on the same board.

- **Chart — create the map**: `POST /1/cards?idList=<Maps>&name=<effort> map&desc=<body>`, then label `wayfinder:map` (`POST /1/cards/<cardId>/idLabels?value=<labelId>`).
- **Create ticket**: `POST /1/cards?idList=<Frontier>&name=<question as title>&desc=## Question ...`, then labels `wayfinder:<type>` + project. Create-then-wire: all tickets exist before blocking lines reference them.
- **Wire blocking**: `PUT /1/cards/<cardId>?desc=<desc with Blocked by: <shortUrl>, ...>`.
- **Frontier query**: `GET /1/lists/<Frontier-id>/cards?fields=name,desc,idMembers,shortUrl,idList`; keep cards with empty `idMembers` whose every `Blocked by:` card is in `Done` (check each: `GET /1/cards/<shortUrl>?fields=idList`). First in list order wins.
- **Claim**: `PUT /1/cards/<cardId>/idMembers?value=<myMemberId>`, then `PUT /1/cards/<cardId>?idList=<In Progress-id>`.
- **Resolve**: `POST /1/cards/<cardId>/actions/comments?text=<answer>`, `PUT /1/cards/<cardId>?idList=<Done-id>`, then GET the map card and PUT its description with the new Decisions-so-far line.
- **Research tickets** fire as parallel subagents; each resolves its own card (claim → work → resolve) so concurrent sessions never touch the same card.

## Bugs and recurrence

A bug tied to tracked work never becomes an isolated card:
1. Check the epic's `## Work items` for a `bug` card in the same area. Open one → comment (`recurred <date>: <symptom>; suspicion: ...`) + epic `## Log` line. Closed with the same root cause → REOPEN it (move back to `Frontier`, add the recurrence comment). One card per recurring issue.
2. No matching card → create in `Frontier`, label `bug` + project, `Epic: <shortUrl>` line, index line on the epic.

Bugs outside any epic: same, minus the `Epic:` line — still project-labelled. Two or more open bug cards in the same subsystem → propose an epic for it (hygiene flags this).

## Delegation handoff (board ↔ subagents)

The orchestrator owns ALL board writes; subagents never touch Trello.
- **Down**: a delegation spec for card work must carry the card's context — epic `## Goal` + relevant `## Design decisions`, the ticket's `## Question`, and acceptance criteria (inline for short, `local://` file for long).
- **Up**: when reviewed work lands, the orchestrator updates the board in the same turn: resolve ops, epic `## Work items` line, and distills anything durable into the epic's `## Design decisions` or the project's `Roadmap — <project>` card. The board is long-term memory; decisions that live only in a session are lost.
- **Unfinished at session end**: comment a state snapshot (done / next) on the card; it stays `In Progress` as the handoff.

## Scenario → board action

- Significant work starts — or you notice you are working on something the board does not track: stop, create/locate the epic, create the ticket, then work.
- New personal project surfaces on the board (repo or chat): create its project label + `Roadmap — <project>` card immediately, mention it, keep going. Work-scope project → refuse and say why.
- Design decision crystallizes (grilling, review): epic `## Design decisions` or `Roadmap — <project>` updated the same turn.
- Bug or regression: Bugs and recurrence, above.
- Work lands or is abandoned: card moves; epic index and `## Log` updated; nothing leaves the board unrecorded.

## Session checkpoint & hygiene

Starting dev work in a personal project → ONE board GET (`GET /1/boards/<boardId>/cards?fields=name,labels,idList,idMembers`), then:
1. `needs-triage` cards (yours or the human's) → triage first: fold into epics/tickets or report back. Cards the human adds carry this label.
2. Your claimed `In Progress` cards → resume or release (unclaim + snapshot comment). Claims never rot.
3. The project's `Roadmap — <project>` card → structure the session against it.

After any batch of card creations, hygiene: flag cards with no project label, epic `## Work items` entries pointing at cards no longer in Frontier/In Progress/Done, and subsystems with 2+ open bug cards (propose epic). Fix before proceeding.

omp injects this checkpoint automatically at session start (`omp-board-checkpoint` extension: once per process, with the project's roadmap gist, open epics, and any needs-triage/In Progress cards; skipped only for work-scope cwd). The manual rule above is the fallback — act on what the injection names.

## Parallel sessions

Claims are members-on-cards, so expect concurrent editors. Never edit the map description blind: GET it, modify locally, PUT the whole body back. Claim before any work.
