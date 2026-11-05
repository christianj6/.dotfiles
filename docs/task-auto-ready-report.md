# Report: auto-ready, four breaks fixed (tk-8c1fa7742905)

Spec: `docs/task-auto-ready-spec.md`. Files changed: the two the spec names,
`config/herdr/plugins/lifeview-fallback/lifeview.py` and `test_lifeview.py`,
plus this report. Nothing outside the spec was edited. Not pushed.

## What changed

**A. Readiness is the project's.**
- Items now match on `project` + `target` (`project_items`, `ready_candidates`). The agent-keyed path is out of the auto-ready decision, and `tasks_for` and `OPEN_TASK` are deleted.
- `World` stamps each agent with its project (the git toplevel's basename, the same rule `project_name` uses).
- `tasks_of` is kept, because other callers use it. All three are display or auto-task, none is auto-ready:
  - `autotask_check` (the covering check);
  - `Harness.auto_task` (its cheap pre-check);
  - `explain` (its per-agent task list).

**B. One predicate over hub states.**
- `hub_open(t)`: any hub state but `done`. It is used for display and for the invariant.
- `ready_candidate(t)`: open and not `ready`. This is the auto-ready set, named separately.
- `hub_state(t)` reads bro's `hub_state` field when bro's list is the source, and the hub's `state` otherwise.
- `BRO_STATES` now carries a "DISPLAY ONLY" comment. It is not chained to anything.

**C. The project settles on its omp.**
- `settler_of(group)` picks the project's only omp. A project with no omp falls back to its only Claude; several omps count as ambiguous and nothing is marked.
- `evidence_of(...)` picks whose transcript the tail check reads:
  - the Claude, when one exists and did the work (the item targets `dev`, or the Claude's transcript moved after the item was handed over);
  - otherwise the omp.

  A Claude is never required.
- `Harness.ready_plans` returns, per project, `{settler, worker, path, tail}`. `path` is the file read for the tail check, and the tests assert it.

**D. Untouched guards:**
- settled;
- no other agent in the project busy;
- the tail is a finished answer;
- the settle window;
- the answer is newer than the last move;
- the last message isn't a question;
- not started by the agent;
- one item only;
- "only the owner drops";
- every provenance rule.

The started-by-the-agent guard is unchanged, but it now gets data. Hub list items carry no history, so `bro_tasks_via_hub` attaches each open item's event log (`/api/tasks/<id>`) as `history`. The guard's keys also gain the hub role `agent`, because hub events record a role, never a herdr name. Without both, the guard would have been silently inert on hub items: a false-green risk.

## Two more breaks found on the way (beyond the four)

5. **`hub_mark_ready` sent `by: <herdr name>`, and the hub refuses that.** `_check_role` accepts only owner, agent, harness or bro. It now sends `by: "harness"`. The success check also read `got["task"]`, which only bro returns; the hub answers `item`. Both are now read.
6. **The hub allows `ready` only from `working`** (`TRANSITIONS`). A `queued` candidate is now started and then marked, both `by: harness`, so the event log says so. `created`, `parked` and `undelivered` have no harness route:
   - `create` queues at once;
   - `unpark` and `retry` are someone else's call.

   So those three are reported in the reason ("no harness route") and never marked.

## Per-state predicate table (printed by `HubPredicate.test_every_hub_state`)

```
state        open  candidate  route         ready_check (lone item, settled omp)
created      True  True       -             no: tk-h1 is created: the hub has no harness route from there to ready
queued       True  True       start+ready   MARK: settled 120s after answering; one open task tk-h1
working      True  True       ready         MARK: settled 120s after answering; one open task tk-h1
ready        True  False      -             no: nothing open in proj awaiting ready
parked       True  True       -             no: tk-h1 is parked: the hub has no harness route from there to ready
undelivered  True  True       -             no: tk-h1 is undelivered: the hub has no harness route from there to ready
done         False False      -             no: nothing open in proj awaiting ready
```

`done` with `resolution=dropped` is never a candidate either (tested). Bro-local names (`open`, `sent`, `reopened`, `noted`) are not hub states, so they are never candidates.

## Acceptance (all in `test_lifeview.py`)

| # | Test | Shows |
|---|---|---|
| 1 | `ProjectAutoReady.test_1_no_claude_…` | A queued coordinator item becomes `ready`. The hub calls are `[start, ready]`, both `by: harness`, with the omp's answer as the summary. |
| 2 | `test_2_claude_present_…`, `2b`, `2c` | The project settles on the omp, and `path ==` the Claude's file, which is also in the scan log. The summary is the Claude's answer. 2b: the Claude was idle since the handover, so the omp's file is read. 2c: a `dev` item reads the Claude, and a project without one still goes ready. |
| 3 | `HubPredicate.*` | The table above, asserted per state. |
| 4 | `test_4_…` | Every row status × every other state plus one `ready` gives `project_icon == ready`. A lone `ready` item makes no hub call (never re-marked). **This is my half only.** Prescient's `status()` half is routed separately and not tested here. |
| 5 | `test_5_…` | Done items only (accepted and dropped) give `idle`, the reason "nothing open", no plan, no hub call and no transcript read. |
| 6 | full file | `python3 test_lifeview.py`: **67 tests, OK** (57 before plus 10 new). |

`test_guards_still_hold_on_the_project_path` also shows three guards blocking on the new path: another agent busy, a question, and an item started by the agent.

## Test changes I made (no assertion weakened)

- **Fixtures** moved to the hub's shape:
  - `agent()` gained `project`;
  - `task()` gained `project` and `target="dev"`. It stands for a Claude workhorse; `coordinator` there would trip `is_coordinator` in the auto-task tests;
  - the eight bro-local `state="sent"` became the hub's `queued`.
- **`test_dest_only_task_matches_and_other_agents_do_not`** tested the agent/dest path the spec deletes, so it is replaced by `test_items_match_on_project_never_agent_or_dest`:
  - an item with neither agent nor dest matches;
  - an agent field naming someone else still matches, since readiness is the project's;
  - another project's item doesn't match, and neither does a non-role target.

## What I ran

- `python3 config/herdr/plugins/lifeview-fallback/test_lifeview.py`: 67 OK. The old suite on the old code was 57 OK.
- `lifeview.py --explain` against the live hub, read-only (GETs only):
  - dotfiles now resolves `tk-8c1fa7742905`, settles on `omp-v25-wdp9`, and reads the Claude's transcript. The old code said "no open bro task" for every project.
  - On bro, the started-by-agent guard fires from hub events (`tk-b964b22eb4ba`).

## Deliberately not done

- **The live daemon wasn't restarted.** herdr runs the plugin from this repo, but the running process keeps the old code until it restarts. The coordinator's live check of cases 1–2 needs that restart.
- **Prescient's `status()` half of acceptance 4** is outside this repo and routed separately, as the spec says.
- **The bro-hub path (`TASK_HUB=bro`)** still posts bro's `ready` action with no start-first step. The live config is `prescient`, so I left it.
- **Observed, not fixed (outside this spec, worth a separate item):**
  - `autotask_check` calls `is_coordinator(tasks)` with the whole hub list. One coordinator item anywhere disables auto-task for every agent.
  - `COVERING` uses bro vocabulary, so a hub `queued` item doesn't "cover".
  - The hub's create ignores `note`, so the harness's session marker is lost on the hub.
- **One consequence of the spec's predicate to decide on:** `parked` and `undelivered` count as candidates. One of them sitting next to a working item makes the project "2 open items: ambiguous", so it never goes green. Narrowing the candidates to `READY_ROUTE` states would change that. I kept the spec's definition.
