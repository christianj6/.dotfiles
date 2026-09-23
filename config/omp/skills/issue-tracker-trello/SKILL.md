---
name: issue-tracker-trello
description: Trello-backed issue tracker for wayfinder and task triage — the "Development" board. Read before any wayfinding operation or when publishing or fetching tasks on the board.
---

# Issue tracker: Trello (Development board)

Issues, wayfinding maps, and cross-project tasks live on the Trello board **Development**. All operations are Trello REST calls with credentials from `~/.dotfiles/.env`:

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

- **Board**: `Development`. **Lists** are the pipeline: `Maps` (wayfinding maps + per-project context cards), `Frontier` (ready, unclaimed tickets), `In Progress` (claimed tickets), `Done` (resolved or ruled out).
- **Map**: a card in `Maps` labelled `wayfinder:map`. Its description IS the map body, sections exactly: `## Destination`, `## Notes`, `## Decisions so far`, `## Not yet specified`, `## Out of scope` (semantics as in `skill://wayfinder`).
- **Ticket**: a card on the same board labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`) plus a project label (`prescient`, `dotfiles`, `thor`, ...). Description starts with `## Question` and the question; a `Blocked by: <card shortUrl>, ...` line sits at the top when blocked.
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

Board `POST /1/boards?name=Development&defaultLists=false&prefs_permissionLevel=private`; lists via `POST /1/lists?idBoard=<boardId>`; labels via `POST /1/labels?idBoard=<boardId>`: `wayfinder:map` (green), `wayfinder:research` (blue), `wayfinder:prototype` (purple), `wayfinder:grilling` (yellow), `wayfinder:task` (orange), `context` (sky), `needs-triage` (red), `ready-for-agent` (lime), `ready-for-human` (pink), `wontfix` (black).

## Wayfinding operations

Used by `skill://wayfinder`. The **map** is a card in `Maps`; tickets are cards on the same board.

- **Chart — create the map**: `POST /1/cards?idList=<Maps>&name=<effort> map&desc=<body>`, then label `wayfinder:map` (`POST /1/cards/<cardId>/idLabels?value=<labelId>`).
- **Create ticket**: `POST /1/cards?idList=<Frontier>&name=<question as title>&desc=## Question ...`, then labels `wayfinder:<type>` + project. Create-then-wire: all tickets exist before blocking lines reference them.
- **Wire blocking**: `PUT /1/cards/<cardId>?desc=<desc with Blocked by: <shortUrl>, ...>`.
- **Frontier query**: `GET /1/lists/<Frontier-id>/cards?fields=name,desc,idMembers,shortUrl,idList`; keep cards with empty `idMembers` whose every `Blocked by:` card is in `Done` (check each: `GET /1/cards/<shortUrl>?fields=idList`). First in list order wins.
- **Claim**: `PUT /1/cards/<cardId>/idMembers?value=<myMemberId>`, then `PUT /1/cards/<cardId>?idList=<In Progress-id>`.
- **Resolve**: `POST /1/cards/<cardId>/actions/comments?text=<answer>`, `PUT /1/cards/<cardId>?idList=<Done-id>`, then GET the map card and PUT its description with the new Decisions-so-far line.
- **Research tickets** fire as parallel subagents; each resolves its own card (claim → work → resolve) so concurrent sessions never touch the same card.

## Parallel sessions

Claims are members-on-cards, so expect concurrent editors. Never edit the map description blind: GET it, modify locally, PUT the whole body back. Claim before any work.
