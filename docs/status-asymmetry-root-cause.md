# The green/amber asymmetry: `status()` picks one row and one role

## Symptom

prescient marks itself green when it has work ready for review. Other projects (thor-voiceai) go amber → **grey**, never green.

## Root cause — reproduced, not inferred

`prescient/tasks/status.py:54-78`. Given a project, `status()` resolves **one** board row and ranks **only that row's role's items**:

```python
rows = [a for a in board["agents"] if a["project"] == project]
row  = next((a for a in rows if a["kind"] == "omp"), None) or (rows[0] if rows else None)   # prefers the omp
target = ROLE_OF_KIND.get(row["kind"], "dev")        # omp -> "coordinator", everything else -> "dev"
items  = store.list_items(project=project, target=target, limit=1000)   # ONLY that role
```

Two consequences, both live right now:

**1. A ready item is invisible when it belongs to the other role.** dotfiles has a `ready` **dev** item:

```
tk-b27f9fce263c | dotfiles | dev | ready
```

Yet the project reports `working`:

```
$ /api/tasks/status?project=dotfiles
  omp-v25-wdp9 | working | it is busy with something nothing here tracks

$ /api/tasks/status?project=dotfiles&agent=claude-v2-wdpa
  claude-v2-wdpa | ready | a task is ready for your verdict
```

The same project, the same moment: green when asked about the dev agent, amber when asked about the project. The plugin asks about **the project**, so it shows amber and the ready work is never surfaced.

**2. A project with no agent for its work's role can never show green.** thor-voiceai runs **one omp pane and no Claude**:

```
agents: omp-v35-wgp1 (omp, working)
items : every recent one is target=coordinator, all done(cleared/dropped)
```

Its row is the omp → `target = "coordinator"`. So its coordinator items rank. But the work an agent does and *reports ready* is stamped to whatever target it started under; when that is `dev` and **no dev agent exists in that project**, there is no row to carry it and no row that ranks `dev` items. Result: `working` while busy, then `idle` = grey the moment it stops — never green.

That is "amber → grey" exactly: amber from the agent's own `working` (liveness), grey because nothing tracked is open once it finishes.

## Why prescient looks right

prescient has **both** an omp and a Claude, and its work has been on the coordinator target, so the omp row it prefers happens to be ranking the items that go ready. The behaviour is correct **by coincidence of which role did the work**, not by design.

## The fix

`status()` must be a function of the **project's items and all its agents**, not of one preferred row:

1. **Rank every open item of the project, whichever target.** A `ready` item is `ready` whether it belongs to `coordinator` or `dev` — the owner is being asked to look at work, not at a role.
2. **Do not prefer the omp row for ranking.** Keep `agent` in the answer for *which row's name* to show, but stop letting that choice decide which items count.
3. **Fall back to the most urgent item when no row matches its role.** If no dev agent exists and a dev item is ready, the project is still green — with `agent` naming whoever is running (or `null`), and `why` saying a task is ready.
4. Keep `AGENT_VOCAB` liveness as a *floor* under the items, never above a ready item: an open `ready` outranks the agent's own `working`, because the owner's attention is the scarce thing.

Invariant to test: **for any project, if any item is `ready`, the project's status is `ready`** — regardless of target, regardless of which agents exist. That single assertion kills both halves of this bug.

## Second-order: the same gap in the board

`ROLE_OF_KIND = {"omp": "coordinator"}` exists only so the icon's row matches the items it carries. Once ranking stops depending on the row's role, that mapping can be reduced to what it actually is: a label for which pane to name. Worth removing rather than widening.

## Verify

1. `status("dotfiles")` → `ready` right now (it has `tk-b27f9fce263c`), not `working`.
2. `status("thor-voiceai")` → follows its items, and when a coordinator item is `ready` it shows green despite having no Claude.
3. All five projects: the "any ready ⇒ ready" invariant holds.
4. A project with nothing open still says `idle` / "nothing open" — the history-only case must not regress.
