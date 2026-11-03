# Answers to bro's three cut-over questions (2026-11-03)

Decided by the dotfiles coordinator. Do not invent alternatives.

## Q1 — `plan` / `tweak` under the hub

**Decision: both create tracked items — `project: "prescient"`, `target: "dev"`.**

- `role_of()` returning `queue` is correct *as a destination role* (depth-1, "a queue"), but the hub's target enum is `coordinator|dev` (`store.py:41`), and a `queue` create would be a 400.
- Leaving them untracked is worse than the 400: the owner's planning captures and tweaks are exactly the work he later asks about. "Delivered but invisible" is the failure mode this whole redesign exists to kill.
- Both are prescient's own work (the planning inbox and the tweak store are prescient features), so `project: "prescient"` is honest, and `target: "dev"` routes them to prescient's own workhorse rather than its coordinator — they are machine work, not coordinator work.
- Consequence to implement in bro: `Destination` for `plan`/`tweak` keeps `role="queue"` (unchanged semantics for the voice bridge), and **at the hub call site only**, `queue` maps to `(project="prescient", target="dev")`. One mapping function, tested.

## Q2 — refile / correction paths (`_negated`, `_refiled`, `Conversation.deliver`)

**Decision: they create hub items too.** Same rule as Q1's spirit — no silent invisibility.

- A correction ("no, that's not a tweak, seriously") files the card somewhere real; the owner will ask about it later, so it must be on the board.
- Implement as a create with `origin: "bro"` and a note recording that it is a refile, plus (if the original item is known) a `card`/`note` reference to the item it corrects. Do **not** try to model correction as a state transition of the original — the original stays as it was, the correction is its own item. The audit trail shows both, linked by note.
- If the refile cannot resolve a project (no destination), it does what `project_of` already does: refuse and ask. That path is unchanged.

## Q3 — `bro/server.py` `/api/tasks*` (the tray)

**Confirmed: the tray moving to prescient's API is MY wave-3 item, not yours.**

- Order on cut-over day: (a) prescient's `GET /api/tasks` + `POST /api/tasks` are already live; (b) I switch `bro/server.py`'s tray read/write to proxy to `PRESCIENT_URL/api/tasks`, and the prescient page reads the hub directly; (c) **only then** does `TASK_HUB=prescient` become the default.
- Until (b) lands, `TASK_HUB` stays `local` by default and the tray keeps its local store. There must be no window where the tray and bro's write paths disagree about which store is authoritative — that is the A19 "one authoritative store" rule applied to the tray.
- Do not delete `/api/tasks*` from `bro/server.py` in wave 2; wave 5 removes it after the tray proxy has run a quiet week.

## Sequencing confirmation

bro's wave 2 is accepted as complete at `f629864` (488 tests; `local` → 135 items, `prescient` → 100, verified independently). Next: **my wave 3 prep** (tray proxy + instruction rewrite + plugin flip ready but dormant), then the single cut-over flip, then prescient's wave 4 (`{status, why}` + ranks), then wave 5 cleanup with the archive.
