# Hub hardening — landed and verified (2026-11-03)

Three fixes landed across prescient and bro today. All verified by me against the live tree, not taken from reports.

## 1. Hub tasks' try / press / reopen reach a live agent — prescient `85d704a`

The owner's `tk-42e749d2f842`. Hub items carry `agent: null`, so `act()` refused every button and **silently dropped "not quite" comments**.

`_live_agent(task, agents)` (agent_board.py:476) resolves per click: the stored agent while it runs, else the project's agent for the task's role (`coordinator → omp`, `dev → claude`). Used at try, tell, press, reopen. Nothing written back.

I verified independently:
- real board row `tk-cbbc4b8a61dc` — `agent=None, project=bro, to=dev` → **`claude-v2-wdp6`**
- dead stored name `omp-v31-whatever` → `claude-v2-wdp6`; no agents in project → `None`
- reopen `ring`s the resolved agent; bell entry addressed to `claude-v2-wdp6`
- ordering: resolve → **raise** → then bro's write, so a comment can never be reopened into nobody
- `DOORBELL_PATH` redirected for my checks; the real queue was untouched

## 2. Unattributed task mutations are refused — prescient `f9c305f`, bro `41b5d11`

**Downgraded from an incident to hardening.** There was no incident: the owner clicked those drops themselves. What remained was that `by` defaulted to the owner on both docks, so a future caller that omitted it would produce an owner-authored event indistinguishable from a real click. That is a weakness in the audit record, not a live fault. No task was repaired on account of it, and the specs say so.

- prescient: `server.py` no longer substitutes a role; an anonymous mutation is a 400.
- bro: `hub_by()` raises `AnonymousActor` on empty; `OWNER_TOKENS` requires an explicit owner token.
- Verified: `''` → `AnonymousActor`, `'harness'` → `'harness'`, `'omp-v34-wdp5'` → `'agent'`, `'the owner'` → `'owner'`.

## 3. Cross-repo seam (this decides whether the owner's test works)

prescient's tray writes `{"by": "the owner"}` by construction (`_bro_task_write`, agent_board.py:492) — only ever from the owner's own click. bro's `OWNER_TOKENS` includes `'the owner'`. Checked the actual join:

```
real row tk-cbbc4b8a61dc (agent=None, to=dev) → _live_agent → claude-v2-wdp6
taskhub.hub_by('the owner') → 'owner'
```

So the refusal does **not** break try/press/reopen. If prescient ever gains a non-click writer, it must send its own identity — recorded here so it is not rediscovered by breakage.

## 4. Stale-bell sweep — prescient `e646dfb`

Bells addressed to agents that no longer exist could never be delivered. Now pruned only when herdr's listing has no agent by that name **or** pane id — a busy or untypeable agent keeps its line. Unknown ≠ dead: if the listing can't be read, nothing is pruned and it says once that the sweep was skipped.

Verified: `data/agent-doorbell.json` is `{"bells": []}`; the trail holds all 3 pruned entries with `pruned_at 2026-11-03T14:25:16Z`.

Also fixed in passing: a bell addressed by **pane id** was kept but never delivered, because the delivery state map was keyed by agent name only. Now keyed on name or pane id.

## State

- prescient: 821 tests, hub intact through the restart (126 items).
- bro: 561 tests, `41b5d11` **not pushed** (4 ahead).
- **Voice stays down** — no `bro voice mic` process. The owner's test is pending and must exercise the fixed try/press/reopen path.

## 5. Voice up — verified at 2026-11-03 15:29

| Process | PID | Mode it actually sees |
|---|---|---|
| `bro serve` | 44537 (up 1h10m+) | `{"mode": "prescient", "source": "env"}` |
| `bro voice mic --live` | 24739 | telemetry run `20261103-152908`, `{"kind":"task_hub","source":"file","task_hub":"prescient"}` |

Both prescient, one store, and the core's split guard passed (it refuses to start if it disagrees with serve — the guard that would otherwise let the two halves write different stores).

`/api/tasks`: **126 rows, 126 hub-backed, 0 non-hub.** First row `tk-cbbc4b8a61dc working hub=true hub_state=working bro/dev`.

### Build staleness is a real hazard, now documented

The first launch after the rebuild failed with `contract mismatch: core 10, brain 11`. Confirmed the mechanism rather than assuming it: `contract/contract.go` uses `//go:embed contract.json`, and `contract.json` now reads `"version": 11`, while the running `bin/bro` carries `"version": 11` after the rebuild. So a stale binary genuinely embeds the old number, and the refusal is the contract working as designed — not a code defect.

**Rule: run `make` before starting the core after any round that touches the contract.** The failure mode is a clean refusal, which is the good case; the bad case would be two halves agreeing on a stale contract.
