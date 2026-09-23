---
name: issue-tracker-trello
description: Trello-backed issue tracker for wayfinder and task triage — the "Development" board. Read before any wayfinding operation or when publishing or fetching tasks on the board.
---

# Issue tracker: Trello (Development board)

Issues, wayfinding maps, and cross-project tasks live on the Trello board **Development**. **Scope: personal development only — system work (dotfiles, omp/herdr tooling) and personal projects. The work space (Tallence: thor, telia, ...) is out of scope and stays in work trackers.** All operations are Trello REST calls with credentials from `~/.dotfiles/.env`:

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
- **Map**: a card in `Maps` labelled `wayfinder:map`. Its description IS the map body, sections exactly: `## Destination`, `## Notes`, `## Decisions so far`, `## Not yet specified`, `## Out of scope` (semantics as in `skill://wayfinder`).
- **Ticket**: a card on the same board labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`) or `bug`, plus **exactly one project label** (`prescient`, `dotfiles`, ... — resolve from the repo you are in; unknown project → ask the user, never guess). Description starts with `## Question` and the question; a `Blocked by: <card shortUrl>, ...` line sits at the top when blocked, and an `Epic: <epic shortUrl>` line when it belongs to a workstream.
- **Epic (workstream)**: one long-lived card in `Maps` per significant chunk of work (e.g. `Mesh Rendering — prescient`), labelled `epic` + project. Description sections: `## Goal` (what done means), `## Design decisions` (durable, agent-facing), `## Work items` (index: `- [<name>](<shortUrl>): <status one-liner>`), `## Log` (dated one-liners: shipped, incidents, recurrences). Every ticket or bug under it carries the `Epic:` line and an index entry. Create the epic BEFORE its tickets.
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
1. Check the epic's `## Work items` for an open `bug` card in the same area. Found → comment on it (`recurred <date>: <symptom>; suspicion: ...`) and add a `## Log` line on the epic. One card per recurring issue.
2. None → create the card in `Frontier`, label `bug` + project, `Epic: <shortUrl>` line, add the index line on the epic.

Bugs outside any epic: same, minus the `Epic:` line — still project-labelled.

## Delegation handoff (board ↔ subagents)

The orchestrator owns ALL board writes; subagents never touch Trello.
- **Down**: a delegation spec for card work must carry the card's context — epic `## Goal` + relevant `## Design decisions`, the ticket's `## Question`, and acceptance criteria (inline for short, `local://` file for long).
- **Up**: when reviewed work lands, the orchestrator updates the board in the same turn: resolve ops, epic `## Work items` line, and distills anything durable into the epic's `## Design decisions` or the project's `Roadmap — <project>` card. The board is long-term memory; decisions that live only in a session are lost.
- **Unfinished at session end**: comment a state snapshot (done / next) on the card; it stays `In Progress` as the handoff.

## Scenario → board action

- Significant work starts — or you notice you are working on something the board does not track: stop, create/locate the epic, create the ticket, then work.
- Design decision crystallizes (grilling, review): epic `## Design decisions` or `Roadmap — <project>` updated the same turn.
- Bug or regression: Bugs and recurrence, above.
- Work lands or is abandoned: card moves; epic index and `## Log` updated; nothing leaves the board unrecorded.

## Board hygiene

At the start of board work: `GET /1/boards/<boardId>/cards?fields=name,labels,idList` and flag (a) cards with no project label, (b) epic `## Work items` entries pointing at cards no longer in Frontier/In Progress/Done. Fix before proceeding.

## Parallel sessions

Claims are members-on-cards, so expect concurrent editors. Never edit the map description blind: GET it, modify locally, PUT the whole body back. Claim before any work.
