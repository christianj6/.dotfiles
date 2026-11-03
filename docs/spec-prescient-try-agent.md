# Fix: "its agent isn't running" on hub tasks' buttons (prescient) — v2

Owner task `tk-42e749d2f842` (dotfiles/dev). Diagnosed read-only by the dotfiles Claude (spec v1 at an earlier path); **I verified every claim against the code and the live board before routing**. The fix belongs in prescient.

## Symptom

The owner pressed "restart bro and try it" on `tk-2a864d0359b8` (bro, `ready`) and got "its agent isn't running".

## Cause — confirmed by reading the code, not inferred

`prescient/gantt/agent_board.py`, four sites, all keyed on a stored agent name that hub tasks never have:

| Line | Action | Failure |
|---|---|---|
| 499 | `try` | `ValueError("its agent isn't running")` |
| 510 | `try`, `how == "tell"` | uses `task["agent"]` after the same check |
| 527 | `reopen` | **silent**: the check is `if task.get("agent") in names:` and the `ring` is skipped, so "not quite — <comment>" is never typed anywhere. The owner's binding feedback is silently lost. |
| 536 | `press` | `ValueError("its agent isn't running")` |

Live board proof (`board(fresh=True)`):
```
tk-2a864d0359b8 | source bro | agent None | project bro | to 'dev' | state ready
tk-8076367bafcd | source bro | agent None | project bro | to 'dev' | state done
tk-735885816f18 | source bro | agent None | project heinzel | to 'dev' | state done
```
`to` **is** on the row (`_from_bro`, line 320), so the resolver has what it needs. `prescient task start|ready` never stamps the agent name, so hub items keep `agent: null` forever.

Stored names also go stale: panes rolled v31 → v34 today, so legacy rows naming `omp-v31-*` fail identically.

## Fix

The resolving rule already exists in this file — `_agent_of` (line 290) — and its comment states the intent: *"a coordinator: whoever in that project takes it (task.agent, once reported)"*. The bug is that `act()` trusts the stored name and never falls back. Keep one rule, add the fallback:

```python
ROLE_KIND = {"coordinator": "omp", "dev": "claude"}   # who takes a role, by kind

def _live_agent(task: dict, agents: list[dict]) -> str | None:
    """The agent for this task, now: its own if still running; else its project's agent for its role."""
    if task.get("agent") and task["agent"] in {a["name"] for a in agents}:
        return task["agent"]
    kind = ROLE_KIND.get(task.get("to") or "")
    for a in agents:
        if a.get("project") == task.get("project") and (kind is None or a.get("kind") == kind):
            return a["name"]
    return None
```

Replace the check at **all four** sites: 499, 510, 527, 536. At each, resolve once into a local and use it for both the guard and the `ring` call — never `task["agent"]` in the `tell`/`ring` lines.

Requirements:
- **Reopen must not stay silent.** With no resolvable agent it must raise (the page shows why), not drop the comment. Prefer routing the comment somewhere over losing it, but do not swallow it.
- Raise the same user-facing message on a genuine "no live agent for that project" — the line the owner sees should name the project, e.g. `no dev agent is running in bro`.
- Do **not** write the resolved name back into the item on click. Resolution is per-click: today's live agent is not tomorrow's, and a stale stamp recreates this bug.
- Optional, separate, only if trivial: `prescient task start|ready` stamps the acting agent's name from `HERDR_PANE_ID`, so the card can say who did the work. This is cosmetic; skip it if it risks the fix.

## Extra constraint I hit live (this is why the fix must be a resolver, not a stamp)

My own nudge to `heinzel/coordinator` just failed with `omp-v34-w5p1d's REPL is not visible; refusing to type blind`. A live agent can exist while being **untypeable**. `_live_agent` may therefore select an agent whose `ring` then fails — that is acceptable (the bell queues it for the next delivery round, `ring`'s existing behaviour), but the *guard* must not be read as a delivery guarantee. Do not "fix" it by filtering on `agent_status`: a busy agent is still the right target.

## Verify (each must be shown, not described)

1. `act({"action": "try", "source": "bro", "id": "tk-2a864d0359b8"})` → the try line reaches `claude-v2-wdp6` (bro's dev) through the doorbell, and no exception.
2. `act({"action": "press", "source": "bro", "id": "tk-2a864d0359b8", "action_id": ...})` → same, no exception.
3. `act({"action": "reopen", "source": "bro", "id": "tk-2a864d0359b8", "comment": "not quite - the flag should show the turn"})` → the comment is **in the bell queue addressed to `claude-v2-wdp6`**. Show the bell file entry.
4. A task whose stored agent is dead (`agent: "omp-v31-whatever"`) still resolves to its project's live agent.
5. A task in a project with **no** agent for that role → a clear error naming the project, and for reopen: **no silent drop**.
6. `prescient task list`/board output unchanged for `agent` on the row (no write-back).

## Files

`prescient/gantt/agent_board.py` (the resolver + four call sites), a unit test module beside the existing board tests. Do not touch the hub store schema, and do not change how `to` or `agent` are computed in `_from_bro`.
