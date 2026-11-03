# Import quarantine: disposition (2026-11-03)

The real import took 99 of bro's 135 tasks into the hub. **36 were quarantined** — their agent was not running, so no cwd existed to resolve a project from. Prescient mapped them dest-first (same rule as `a2dab97`).

## Decision: none of them become hub items

| Group | Count | Content | Disposition |
|---|---|---|---|
| → bro | 23 | `agent:claude-bro` / `agent:orchestrator`; 19 done, 4 dropped. Real work ("Show when bro is in standby", "Let bro interact with what's in prescient") | **Durable record only.** Already history; bro's `data/tasks.json` keeps them until wave 5. No hub resurrection. |
| → prescient | 4 | `agent:claude-prescient`, one `dest tweak`; 2 done, 2 dropped | Same. |
| → scratch noise | 9 | `v2-wnp1` ×3, `v2-wrp1` ×2, `v2-wqp1`, `v2-wpp1`, `v2-wmp1` — the dotfiles lifeview plugin's own test tasks ("grey flash", "count lines in words.txt"), all dropped | **Dropped, never preserved.** They are artifacts of our testing, not the owner's work. |
| → `top` | 1 | dest `top`, project None, a retry-message instruction, dropped | Dropped. |

**Why not resurrect:** 31 of 36 are already `done`/`dropped` — bringing them back into the hub would create 31 `ready`-looking or terminal rows the owner must re-adjudicate for no benefit, and would pollute the board the new system is meant to keep clean.

**Why not park the 27 "real" ones to Trello:** they are completed history, not planned work. Trello is the audit log for what the hub *does from now on*; back-filling a year of finished bro tasks buys nothing the git history and `data/tasks.json` do not already hold.

**Durability gap, accepted:** bro's `data/tasks.json` is deleted in wave 5. To keep the 27 real ones retrievable, wave 5's deletion step should **archive the file** (e.g. `data/archive/tasks-pre-hub.json`, gitignored, never deleted) rather than unlink it, and note the path in bro's AGENTS.md. That is a one-line change to wave 5, recorded here so it is not lost.

## Rule for future imports

Quarantine is a **report**, not a queue: the operator decides per group, and the default is "leave it in the source store, archive the source". Never auto-create hub items from quarantined rows.
