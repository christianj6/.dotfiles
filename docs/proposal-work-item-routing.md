# Proposal: one work item, one route, one state machine

Response to the owner's brief (2026-11-02/03): *"if I tell bro to have something happen in a project, a task should be created… routed efficiently and reliably to that project's coordinator without interrupting it… the coordinator decides: work now with claude, hold until claude stops, kick to Trello… everything represented once, status and routing lean."*

Inputs: my survey (dotfiles side) + claude's survey (`/tmp/ws-survey-claude.md`) + code read of `bro/{tasks,stack,agent,delivery}.py`, `prescient/gantt/{agent_board,inbox}.py`, `lifeview.py`.

---

## 1. What is actually wrong (five structural causes)

| # | Cause | Evidence |
|---|---|---|
| 1 | **Three state resolvers** for one agent's status (prescient `_own_status`, plugin `decide`/`stale_override`, then `agentGroups` ORing herdr back in) plus **hard-copied tables** (`AG_RANK`, `BRO_STATES`, `OPEN`) in three files | `agent_board.py:196-232`, `lifeview.py:66-75,186-260`, `index.html:9137,9164` |
| 2 | **Routing is inferred from a string**, never declared: `_project()` slices `dest` (`agent:claude-v2-w5p1a` → `v2-w5p1a`; `agent:omp-…` → `None`) | 61 harness tasks: **38 `project: None`**, 23 garbage |
| 3 | **Identity is a herdr name**, which encodes version+pane and drifts on every roll → orphaned tasks, ghost icons; status files keyed by **reusable pane ids** | `omp-v31-wdp7`; stale `wD:p5` entry |
| 4 | **Four notification channels** with different guarantees: bro `delivery.py` (retrying), prescient doorbell, prescient `omp-peer --no-guard` fire-and-forget, prescient ping→inbox | `delivery.py:57-87`, `agent_board.py:413-442`, `bro_stack.py:154` |
| 5 | **`sent` means two things**; no transition rules; `move()` accepts any state from anyone; harness "ready" recorded `by: <agent>` | `tasks.py:90-113`, `cli.py:119-120` |

Symptom the owner feels: tasks land on the wrong agent or nowhere, icons lie, the same work is announced three ways, and auto-tasks add noise (61 of 129 tasks; 50 closed/10 dropped by the owner).

---

## 2. Target model (what "simple and clean" concretely means)

### 2.1 One entity: the **work item**

A single record, owned by **bro**, with explicit fields — no inference:

```
id            tk-…
text          the owner's words
project       EXPLICIT repo name, given at creation (never derived from dest)
target        the destination id it was routed to ("coordinator:heinzel")
origin        owner | agent | harness            <- replaces the ambiguous `sent`
state         see the machine below
history[]     {at, state, by: owner|agent|harness|bro, note}
```

`project` + `target` are **required** at creation. `bro task add --project X --dest coordinator:X`; HTTP `POST /api/tasks` gains the same two fields (today it has no create at all — claude's finding).

### 2.2 One state machine, enforced

```
created ──route──> queued  ──agent pulls──> working ──agent done──> ready ──owner──> done
                     │                                              │
                     ├─ coordinator declines ─> parked (→ Trello)   └─ owner: not quite ─> working
                     └─ delivery fails ───────> undelivered (retries, then surfaces)
```

- **`queued`** = waiting in the coordinator's inbox (route accepted). **`working`** = an agent is on it. **`ready`** = an agent says "look at this". **`undelivered`** is a real, visible state (not `failed` after 1s).
- Transitions validated in one place (`tasks.move` gets an allowed-transition table); `by` is an enum of roles.
- `sent` disappears: it's `queued` with a delivery receipt.

### 2.3 One route: the coordinator's inbox

- bro resolves `project` → the project's coordinator **by declared identity, not name**: a small registry (per-repo file `prescient-coordinator.json` or a field in `docs/DEV_BOARD.md`) naming the repo's coordinator role. The herdr name is resolved *at read time* from `herdr agent list` by cwd — so a version bump doesn't orphan anything.
- Delivery is **non-interrupting by construction**: the item lands in the coordinator's queue (a file), and the coordinator is *notified*, never typed into. The coordinator drains on its own turn boundary.
- **One delivery implementation**: `omp-peer` (dotfiles owns it) with a documented exit-code contract; bro and prescient both call it. `--no-guard`, fire-and-forget and the doorbell go away.

### 2.4 One status write, one resolver

- Agents write **intent only** (`working|standby|blocked|idle`) via `prescient status`; the harness writes **observed** state; both land in per-repo files keyed by **`(repo, role)`**, not pane id.
- **prescient resolves**: `resolved_status = f(herdr, agent_intent, harness_observed)` returning `{status, why, inputs}` in `/api/agent-board`. The plugin stops re-implementing precedence and just reads `why` for `--explain`. Tables (`AG_RANK`, `BRO_STATES`, `OPEN`) move to **one** shared definition.

### 2.5 Two channels, no third

- **Oversight** (transient): the work item above — what's happening now, what's ready for a verdict. Icons.
- **Planning** (durable): Trello card / repo doc. A work item that turns out to be multi-session gets **promoted**: `bro task park --card <trello shortUrl>`, which closes the item and records the link. No duplication: the item references the card, never restates it.

### 2.6 Auto-tasks, quietened

Keep the mechanism (it makes green real without agent cooperation) but change the trigger from "2 tool calls" to **"a work item already exists for this work"**:
- If the coordinator created an item → the harness never auto-creates.
- If work starts with **no** item → auto-create **one** item per agent per *session*, `origin: harness`, and give the UI a single "accept all harness items" button instead of N verdict clicks.
- Trivial lookups never auto-create (keep the 2-call/90s floor).

---

## 3. What I'd do, in order (each step independently shippable)

**Step 1 — stop the bleeding (small, dotfiles + bro).**
`project` becomes an explicit argument on `bro task add` + a `POST /api/tasks` create endpoint; the harness passes the git toplevel's basename. Kills 38 `None` projects immediately. *(bro's side; dotfiles passes the field.)*

**Step 2 — one delivery path (dotfiles).**
Document `omp-peer`'s exit-code contract in the repo; bro's `delivery.py` and prescient's doorbell both call it; delete the fire-and-forget and the doorbell. Retries stay in bro (it owns the receipt).

**Step 3 — one resolver (prescient).**
Move precedence into `agent_board`, publish `{status, why}` in `/api/agent-board`; the plugin writes inputs only and reads `why`. Delete the plugin's copied tables. This is the root-cause fix for today's whack-a-mole.

**Step 4 — stable identity (dotfiles + prescient).**
Per-repo coordinator identity file; status entries keyed `(repo, role)`; name resolution at read time. Kills orphaned tasks and reused-pane-id collisions.

**Step 5 — the state machine (bro).**
Allowed transitions, `origin`, role-typed `by`, `undelivered` as a visible state, park→Trello.

**Step 6 — quiet auto-tasks + batch accept (dotfiles + prescient UI).**

---

## 4. Risks / open questions for the owner

1. **Where does the work item live?** I propose bro (it already has the store, locks, CLI and HTTP). The alternative — a per-repo queue file like `prescient-status.json` — would make routing local and remove a central dependency, but duplicates store logic. **This is the biggest design decision** and it changes steps 1-5.
2. **Trello promotion**: automatic (item goes `parked` when it exceeds a threshold) or always the coordinator's explicit call? I'd keep it explicit.
3. **Auto-accept**: is a single "accept all harness items" click enough, or should harness items not produce green at all (only agent-acknowledged work greens)?
4. **Do we keep the inbox at all?** With one route and one queue, `ping` and tweaks may collapse into the same work-item stream.

## 5. Recommendation

Do **Step 1 + Step 3 first** (they're small and kill the two biggest complaints: wrong-project routing and lying icons), then decide question 1 before touching the rest — because the work-item's home determines everything downstream.
