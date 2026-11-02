# Life-view automation verification

Run 2026-11-02 on herdr 0.9.5, with prescient (`/api/agent-board`, port 8765)
and bro (`/api/tasks`, port 8766) live. Times are local. Lines tagged
`[lifeview-fallback]` come from `/tmp/lifeview-fallback.log`. The scratch agent
ran in a throwaway git repo (gitignoring the status file) in its own herdr
workspace, closed afterwards.

Plugin: `config/herdr/plugins/lifeview-fallback/lifeview.py` (extended, not a
new plugin). The first version's evidence is `docs/lifeview-fallback-verification.md`.

## Result

| Case | Result |
| --- | --- |
| 1. Working → amber without any agent CLI call | Pass: board `working` from +10 s while herdr said working |
| 2. Settled with an open bro task → green without any CLI call | Pass: task `sent` → `ready` 61 s after the agent's answer, with the auto note |
| 3. Agent-authored entry wins | Pass: `standby "custom line"` survived 8 forced ticks, herdr `working` throughout the first 5 |
| 4. `--explain` | Pass: a green, a dim, and a guarded agent, each with its reason |
| 5. Unit tests (`python3 test_lifeview.py`) | 21 pass (25 with the grey-flash tests below) |
| Bonus: herdr `blocked` → `blocked`, live | Pass: the scratch pane's trust prompt |

## What the plugin does now

Two signals feed the icon (see `agentGroups()` in prescient's `index.html`):
the inner line from `prescient-status.json`, and the ring from bro task state,
where `ready` is green. The plugin feeds both from the harness:

1. **State**: herdr's `agent_status` goes into `prescient-status.json` for every
   agent not speaking for itself. Entries are marked `"by": "harness"` and
   `harness: ...` (first-version `fallback` entries migrate). The precedence
   rules are unchanged from v1: a fresh agent entry (<180 s or within its
   `ttl_s`) always wins, and an agent's stale `idle`/`standby`/`blocked` stands
   until the agent replaces it.
   herdr's status is already harness-derived: omp-watch feeds omp's transcript
   verdict into herdr, and claude's comes from its hooks.
2. **Green**: when an agent settles after answering, its one open bro task is
   marked `ready` through bro's HTTP API (`POST /api/tasks`, `by` = the agent
   so the task stays on its card). The summary is the agent's last message,
   prefixed `auto: `. The note records the provenance and the off-switch.
   `LIFEVIEW_AUTO_READY=0` disables it.

### Auto-ready conditions (all must hold)

Each one closes a way a false green could happen:

| Condition | Guards against |
| --- | --- |
| Exactly one open (`open`/`sent`/`working`) task attributed to the agent (`agent`, else `dest: agent:<name>`) | Picking the wrong task |
| Not a task the agent itself `bro task start`-ed (`LIFEVIEW_AUTO_READY_STARTED=1` overrides) | An agent idle on purpose. Seen live, see below |
| herdr says `idle`/`done` | Mid-turn, blocked on a dialog, unknown |
| No other agent in the same git repo is `working`/`blocked` | A coordinator that settles right after delegating to its workhorse |
| Transcript tail is an assistant answer (text, no tool call), not an API error | A turn cut off mid-tool, or a dead turn |
| Quiet for `LIFEVIEW_SETTLE_S` (60 s) since that answer | Brief gaps between turns |
| The answer is newer than the task's last move | Greening a task on an answer that predates it |
| The answer doesn't end in `?` | An agent asking the owner something |

### Two things the live run changed

- **herdr's claude session id goes stale.** bro's claude pane was claimed by
  a session last written 14 h earlier, while its live transcript was another
  file. For the only claude pane in a cwd, the plugin now takes the newest
  *interactive* transcript (`"entrypoint":"cli"`) in claude's
  transcript folder for that cwd, which skips headless `sdk-cli` runs (the bench
  writes those into the same folder). With two claude panes in one cwd it
  falls back to herdr's id.
- **The false green the spec's rule would have produced.** bro's claude had
  `tk-21e9d0bf2e` in `working` (it had run `bro task start`), was idle, and
  its own line read *"bench rerun running; tk-21e9d0bf2e goes ready when it
  passes"*. Every other condition would have held, so auto-ready would have
  greened a task whose bench hadn't passed. Hence the started-by-the-agent
  exclusion: an agent that ran `start` knows the protocol, so `ready` stays
  its call. Auto-ready covers the tasks no agent acknowledged, which is
  exactly the "forgot the CLI" case.

## 1 + 2. Working → amber, settled → green, no agent CLI call

A bro task routed to the scratch agent (`bro task add ... --dest
agent:claude-v2-wmp1`, so it starts in `sent`), then this prompt: *"Do not run
any prescient or bro commands in this session. Task: first run exactly:
`python3 -c "import time; time.sleep(30)"` in the foreground, then count the
words in words.txt and reply with the number in one sentence."* Sampled every
5 s (herdr / `/api/agent-board?fresh=1` row and task / status file / bro's
`data/tasks.json`):

    before: herdr=['idle'] board.status=idle board.said='harness: herdr idle' board.task=queued | file=('idle', 'harness') | tasks.json=sent
    prompted 10:03:09
    +5s   herdr=['working'] board.status=idle    ... board.task=queued | file=('idle', 'harness')    | tasks.json=sent
    +10s  herdr=['working'] board.status=working board.said='harness: herdr reports working' board.task=queued | file=('working', 'harness') | tasks.json=sent
    ...   (working through +36s)
    +41s  herdr=['done']    board.status=idle    board.said='harness: herdr idle' board.task=queued | file=('idle', 'harness') | tasks.json=sent
    ...   (settling)
    +98s  herdr=['done']    board.status=idle    ... board.task=queued | tasks.json=sent
    +103s herdr=['done']    board.status=idle    ... board.task=ready  | tasks.json=ready
    ...   (ready through +175s)

    [lifeview-fallback] 10:03:16 <scratch repo>: wM:p1 -> working (harness: herdr reports working)
    [lifeview-fallback] 10:03:47 <scratch repo>: wM:p1 -> idle (harness: herdr idle)
    [lifeview-fallback] 10:04:48 bro tk-e19982843a -> ready (auto) for claude-v2-wmp1: settled 61s after answering; one open task tk-e19982843a

The task record in bro's `data/tasks.json` afterwards:

    "state": "ready", "agent": "claude-v2-wmp1",
    "summary": "auto: The sleep ran for its 30 seconds, and `words.txt` contains 3 words.",
    history: open (bro) -> sent (lifeview-verification) ->
      {"at": "2026-11-02T10:04:48+01:00", "state": "ready", "by": "claude-v2-wmp1",
       "note": "auto-marked ready by the lifeview harness: claude-v2-wmp1 settled 61s after its last answer with this as its one open task; summary is that answer. LIFEVIEW_AUTO_READY=0 disables this."}

Every tool command in the scratch agent's transcript (no `prescient`, no `bro`):

    python3 -c "import time; time.sleep(30)"
    wc -w words.txt

Amber lagged herdr by up to one 10 s tick (+5 s sample). The board's ring for
this agent alone went queued → working → queued → **ready**.

## 3. Agent-authored entry wins

The scratch agent ran `prescient status standby "custom line"` itself, then a
20 s foreground sleep, so herdr said `working`, contradicting `standby`. A
harness tick was forced (`lifeview.py --once`) every 5 s, alongside the daemon:

    prompted 10:06:25
    +5s  forced tick: herdr=['working'] file={'state': 'standby', 'at': '2026-11-02T10:06:29+01:00', 'line': 'custom line'}
    +10s ... +25s: herdr=['working'], the same entry
    +30s forced tick: herdr=['done'] file={'state': 'standby', 'at': '2026-11-02T10:06:29+01:00', 'line': 'custom line'}
    +35s, +40s: the same entry

There was no harness write for the pane after 10:03:47.

## 4. `--explain`

    bro: up; prescient: up; auto-ready on

    claude-v2-wmp1 [wM:p1, claude] -> icon: ready
      herdr: done
      transcript: answered, 22s ago  (784d012d-....jsonl)
      prescient-status.json: standby by the agent, 45s old: custom line
      dashboard row: status standby (herdr done)
      bro tasks: tk-e19982843a ready
      auto-ready: no open bro task for it
      why: bro task tk-e19982843a is ready for your verdict (green)

    claude-v2-w5p1a [w5:p1A, claude] -> icon: idle
      herdr: done
      transcript: answered, 870s ago  (6a6dbb9c-....jsonl)
      prescient-status.json: idle by the agent, 873s old:
      dashboard row: status idle (herdr done)
      bro tasks: none open
      auto-ready: no open bro task for it
      why: dim: idle (idle) with no open task needing you

    claude-v2-wdp6 [wD:p6, claude] -> icon: working
      herdr: done
      transcript: answered, 856s ago  (24db546b-....jsonl)
      prescient-status.json: idle by the agent, 861s old: bench rerun running; tk-21e9d0bf2e goes ready when it passes
      dashboard row: status idle (herdr done)
      bro tasks: tk-21e9d0bf2e working
      auto-ready: tk-21e9d0bf2e was started by the agent itself: `ready` is its call (LIFEVIEW_AUTO_READY_STARTED=1 overrides)
      why: working, from bro task tk-21e9d0bf2e (working); the agent's own status is idle

When prescient is down, the icon is computed locally with the dashboard's
ranks. When bro is down, auto-ready is skipped and the header says so.

## Cleanup

The scratch workspace was closed. The scratch task `tk-e19982843a` was dropped
by its creator (`--by lifeview-verification`) so it doesn't sit green in the
owner's list. The scratch repo's last entry was the agent's own `standby`,
which the plugin leaves alone, since it only removes entries of its own.

## False-green risk, plainly

Auto-ready can still show green for a task that isn't done:

- **An agent that never ran `bro task start`, then stops for a reason other
  than finishing**: it reports partial progress, gives up, or waits on a
  background job, and words its last message as a statement, not a question.
  The `auto:` summary then shows what it actually said, so the owner sees
  "ready" alongside the agent's real last words, not a claim of completion.
- **The `?` heuristic is only a heuristic.** "Let me know which you prefer."
  isn't caught.
- **A one-shot answer that isn't the work**: for example, the agent
  acknowledges the task in one turn ("On it, starting after the current
  job.") and settles. It passes every check.
- **Coordinator delegation is guarded only while the workhorse is visibly
  busy.** If the workhorse finishes and the coordinator hasn't woken to review
  within 60 s, the coordinator's task can go green before its review.

A green from auto-ready is always marked: `auto:` on the summary, and the
history note. The owner's `not quite` reopens it as usual. A reopened task
(`reopened`) is not auto-readied again, so the agent's own `ready` is needed
the second time.

## Not tested live

- An omp agent's auto-ready (the transcript reader is the same; omp's file
  lookup is omp-watch's `newest_session_file`, and it is skipped when two omp
  agents share a cwd).
- The project-busy guard firing (unit-tested only).
- `[[startup]]` and exit-on-server-death, as in v1.

## The grey flash between amber and green (fixed)

Owner-reported: during the live icon test the ring went amber → **grey** →
green. It must never pass through grey.

### Cause, measured

For an agent whose task is still `open`/`sent`, the dashboard's ring
(`agentGroups()`) is the best-ranked of the task's `queued` and, while the
agent's row says so, `working`. Once herdr says idle, the harness wrote
`idle`, so `working` dropped out and the ring fell to **`queued`**. That's a
higher rank than `idle`, but `.ag-ic.queued` only sets a dashed border with
the default colour, so it looks grey. It stayed that way for the whole 60 s
settle window, until auto-ready wrote `ready`.

The task never left the board or lost its agent (the spec's first
hypothesis). It was the second: nothing ranked above `queued` while the
settle window ran.

### Fix (plugin only, no prescient change)

While an agent is **settling toward auto-ready**, meaning it would be
marked ready once the settle window has passed with nothing else changing
(`pending()`: `ready_check()` re-run with the clock moved forward by
`LIFEVIEW_SETTLE_S`), the harness keeps its entry at `working`, line
`harness: settling, auto-ready pending`. The entry's `ttl_s` is the settle
window plus three ticks (90 s), so prescient's `_working_believable()`
believes it although herdr says idle, and a dead plugin can't hold it for
long. Every auto-ready guard still applies, so an agent that won't go green
(a question, a task it started itself, a busy project, no task) is never
held. In each tick the task is now marked ready *before* the status write, so
the hold is released only after the ring is already green.

Invariant, unit-tested (`GreyFlash` in `test_lifeview.py`): for an agent with
one open bro task, the ring goes `working` → `ready` with nothing in between,
and a task-less agent still drops to idle on the next tick.

### Before the fix: 2 s samples of `/api/agent-board?fresh=1`

The ring was computed as `agentGroups()` does, for the scratch agent's project,
with one task `sent`. Transitions only (full trace: 69 samples):

    10:21:52 claude-v2-wnp1=working                tasks=['queued'] -> ring=working [amber]
    10:22:20 claude-v2-wnp1=working(herdr done)    tasks=['queued'] -> ring=working [amber]
    10:22:23 claude-v2-wnp1=idle(herdr done)       tasks=['queued'] -> ring=queued  [GREY]
      ... 30 consecutive grey samples ...
    10:23:22 claude-v2-wnp1=idle(herdr done)       tasks=['queued'] -> ring=queued  [GREY]
    10:23:24 claude-v2-wnp1=idle(herdr done)       tasks=['ready']  -> ring=ready   [GREEN]

    [lifeview-fallback] 10:21:52 <scratch repo>: wN:p1 -> working (harness: herdr reports working)
    [lifeview-fallback] 10:22:22 <scratch repo>: wN:p1 -> idle (harness: herdr idle)
    [lifeview-fallback] 10:23:23 bro tk-aebc58a403 -> ready (auto) for claude-v2-wnp1: settled 65s after answering; ...

### After the fix: the identical run

The same prompt and a new task (the earlier scratch tasks were dropped first,
so they show `dropped`, drawn dim, and can't mask the ring). Transitions only:

    10:28:44 claude-v2-wnp1=idle(herdr working)    tasks=['queued', ...] -> ring=queued  [GREY]   (before amber: tick lag)
    10:28:50 claude-v2-wnp1=working                tasks=['queued', ...] -> ring=working [amber]
    10:29:13 claude-v2-wnp1=working(herdr done)    tasks=['queued', ...] -> ring=working [amber]  <- the hold
    10:30:11 claude-v2-wnp1=idle(herdr done)       tasks=['ready', ...]  -> ring=ready   [GREEN]

    grey/dim samples between amber and green: 0 (of 69 samples)

    [lifeview-fallback] 10:28:50 <scratch repo>: wN:p1 -> working (harness: herdr reports working)
    [lifeview-fallback] 10:29:20 <scratch repo>: wN:p1 -> working (harness: settling, auto-ready pending)
    [lifeview-fallback] 10:30:11 bro tk-03a699f5de -> ready (auto) for claude-v2-wnp1: settled 61s after answering; ...
    [lifeview-fallback] 10:30:11 <scratch repo>: wN:p1 -> idle (harness: herdr idle)

An intermediate run (before the ready-first reorder) logged `-> idle` and then
`-> ready` in the same tick. A board read cached between the two writes
(prescient memoises for 2 s) could have shown grey briefly. The reorder closes
that.

### No regression: an agent with no open task

    10:31:23 claude-v2-wnp1=working             -> ring=working [amber]
    10:31:38 claude-v2-wnp1=working(herdr done) -> ring=working [amber]
    10:31:44 claude-v2-wnp1=idle(herdr done)    -> ring=dropped [dim]

    [lifeview-fallback] 10:31:43 <scratch repo>: wN:p1 -> idle (harness: herdr idle)

It was dim 6 s after herdr said done, with no hold.

### Also fixed on the way

A closed pane's harness entry in a repo with no live agent left was never
swept, because ticks only visited repos with live agents. The plugin now keeps
sweeping every repo it has written to (in memory, so it resets on a daemon
restart). Shown live: `wN:p1 harness entry removed` after the scratch
workspace closed.

### Ways grey can still show

- **Before amber, up to one tick (10 s)**: a task `sent` to an agent shows
  `queued` (grey) until the plugin's next tick sees herdr `working`
  (10:28:44 above). This is not between working and ready, but the owner
  can see it. Raising the tick rate would shorten it.
- **An agent that won't be auto-readied** (its last message is a question,
  more than one open task, a busy project) falls to `queued` once idle. That's
  steady grey, not a flash, and arguably right ("waiting for it"). The
  dashboard has no colour for "waiting on the owner's answer".
- **An agent that writes its own `prescient status idle`** without having run
  `bro task start`: its fresh entry wins over the hold, so it's grey through
  the settle window. Agents that follow the instructions run `start`, which
  makes the task `working` (amber) instead.
- **bro's POST fails**: the task stays open and auto-ready no longer passes,
  so the hold is released and it's grey until a later tick succeeds.
- **The plugin dies mid-settle**: the hold's `ttl_s` (90 s) runs out, then
  grey.
