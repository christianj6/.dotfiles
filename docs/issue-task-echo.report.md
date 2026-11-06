# Report: the task echo (docs/issue-task-echo.md)

Committed locally, not pushed. Files changed:
- `config/herdr/plugins/lifeview-fallback/lifeview.py` and `test_lifeview.py`;
- `config/herdr/skills/herdr-workstreams/peer.py` and `test_peer.py`;
- this report.

## To make it live

1. **Restart the lifeview daemon again.** The running one started at 08:26 today, after `30dbf2b`, so it already parses tags. It predates this commit, though: coverage and the comms gate need the restart.
2. **Re-install omp-peer** (setup.sh's `cp …/peer.py ~/.local/bin/omp-peer`). The installed copy matched the repo when this task started; it lacks the stale-name resolution.

## Cause 1: the daemon predated the tag parser (confirmed, already resolved)

- HEAD's `prompt_provenance` reads `TAG` first (`tag = TAG.match(prompt)`, before every shape rule).
- The daemon process now running started at **08:26 today**, after `30dbf2b` (19:51 yesterday), so the restart the issue asks for has already happened. Tags have been read since then.
- One more restart is needed for this commit.

## Cause 2: coverage was agent-keyed (reproduced, fixed)

Reproduced on the code before this change. The hub item is exactly what the hub returns: `agent: null`, no `agent:<name>` dest, `project=prescient`, `target=coordinator`, `working`.

```
tasks_of        -> []
project_items   -> ['tk-open']
worker report   -> ('auto: Both landed, 998 tests OK', 'work session: 3 tool calls, 60s, no task covering it')
```

After the fix:

```
worker report   -> (None, 'covered by tk-open (working)')
```

**The fix:** `covering_items(agent, tasks)` replaces `tasks_of` at **both** coverage sites:
- `autotask_check`'s gate;
- `Harness.auto_task`'s cheap pre-check, which had the same agent-keyed test.

It keys on the project through `project_items`, the same function `ready_candidates` uses, so the auto-task and auto-ready halves now agree on what "covered" means. `tasks_of` survives only as a fallback for bro's own list, whose items do name an agent (tested).

**Choice stated: any in-progress item of the project covers, whatever its target.** I did not split by role. The harness opens every card with `target=coordinator`, whichever pane did the work (`hub_open_task`). So a dev-keyed check for the Claude would never see the harness's own cards, and the echo would come back. A project is one work stream: one omp plus its Claude.

**Also changed: `COVERING` is now the in-progress states.** That is the hub's `created`, `queued` and `working`, plus bro-local `open`, `sent`, `reopened` and `noted`. **`ready` no longer covers.**
- A ready item waits for the owner's verdict, possibly for hours. If it covered, every request the owner made meanwhile would get no card and no lifecycle, which would weaken the owner lifecycle.
- Before this fix it never mattered, because nothing ever covered.
- `parked`, `done` and other projects' items don't cover either (tested).

**The echo is impossible:**
- `test_2_the_echo_is_impossible_end_to_end`: an owner request opens a card. Three more turns in the worker's pane while it is open (a report, a report path, a follow-up), each with its own session key, open nothing. The hub calls are exactly `[create]`.
- **Mutation check:** with both sites reverted to `tasks_of`, this test and `test_2_an_open_project_item_covers…` **fail**. With the fix they pass.

## Cause 3, the owner's priority #1: agent-to-agent comms open no card

Reproduced before the change:

```
tagged dispatch -> ('auto: Read docs/x.md and implement it', 'work session: 3 tool calls, 60s, no task covering it')
```

After:

```
tagged dispatch -> (None, 'an agent-to-agent message ([from:coordinator]): comms, never a card')
tagged report   -> (None, 'an agent-to-agent message ([from:worker]): comms, never a card')
```

`autotask_check` refuses any turn whose prompt carries a `[from:coordinator]` or `[from:worker]` tag, in any project and on either pane kind. This sits right after the machinery check. `prompt_provenance` still answers `agent` for these, because the record of who spoke is unchanged; only carding stops.

Still carded, as the issue proposes:
- `owner` (tagged or untagged human words);
- untagged agent-by-shape prompts (a round spec);
- `[from:bro]`, which is bro relaying, with the owner's words behind it. Narrow it if you want: add `bro` to `COMMS_TAGS`.

This reverses one test from the tag task: `test_a_coordinator_dispatch_is_agent_not_owner` asserted that a tagged dispatch opens an agent card. It now asserts that provenance is `agent` and that **no card** opens: zero hub calls, and the ring idle on both ticks.

## Cause 4: the owner's own pane replies (not changed, the owner's call)

An owner message with a tool call still cards. That is the lifecycle working, and the editorial note says not to weaken it. Whether "owner said anything" should narrow to "owner asked for work" is a judgement about the wording of his messages, so it is the owner's call. Dropping `ready` from coverage doesn't touch this: it only decides whether a second owner request gets its own card.

## omp-peer: stale agent names (fixed)

`omp-peer send omp-v25-wdp9 …` used to fail with herdr's `agent_not_found`. Now omp-peer looks for a live agent with the same kind and the same pane key, differing only in the version part:
- **Exactly one match:** it resolves, prints `omp-v25-wdp9 is stale (the pane rolled); its live agent is omp-v35-wdp9` to stderr, and sends to the live name.
- **Two matches:** it refuses as ambiguous.
- **None:** it refuses, listing the live agents of that kind. A non-auto name refuses as unknown.

A different kind on the same pane (`claude-v2-wdp9`) never resolves to the omp. Live against the real agent list: `omp-v25-wdp9 → omp-v35-wdp9`, `claude-v1-wdpa → claude-v2-wdpa`. This report's notification was sent to the stale `omp-v25-wdp9` on purpose (result at the end).

**On "why one message went out untagged":** in the current code the tag is computed from the **sender's** pane before the target is looked up. A stale target cannot strip the tag: omp-peer exits 1 and sends nothing (`test_6_an_unknown_target_sends_nothing`). The untagged message most likely came from a fallback to bare `herdr agent prompt` after omp-peer refused. I can't verify that from here.

## Acceptance

| # | Check | Covered | Evidence |
|---|---|---|---|
| 1 | Daemon restarted; a tagged `[from:worker …]` message creates no card | **Yes.** The restart already happened (08:26 today, after `30dbf2b`); one more is needed for this commit. | `TaskEcho.test_3_*`: a tagged dispatch in the Claude and a tagged report in the omp, through a full harness tick, give zero hub calls |
| 2 | A worker with an open project item creates no new card; `tasks_of` replaced, echo impossible | **Yes** | `test_2_an_open_project_item_covers…` (`tasks_of` → `[]`, `covering_items` → the item; every in-progress state × both targets), `test_2_the_echo_is_impossible_end_to_end`, plus the mutation check |
| 3 | A coordinator's dispatch to its own worker creates no card | **Yes** | `test_3_*`; `MessageTags.test_a_coordinator_dispatch_is_agent_not_owner_and_opens_no_card` (a full lifecycle run: no item, rings idle, idle) |
| 4 | An owner request in a pane still creates one card and completes | **Yes** | `test_4_owner_requests_still_card_and_complete_one_after_another`: two requests, the second (tagged `[from:owner]`) arriving while the first sits `ready`, give two owner cards, both `ready`, and the ring green each time. The existing `OwnerLifecycle` and `MessageTags` lifecycle tests are unchanged and pass. |
| 5 | Untagged messages behave as today | **Yes** | `test_5_*` (the four classes, and a round spec still cards). All pre-existing untagged tests pass unmodified; the one changed test is about a *tagged* dispatch (Cause 3). |
| 6 | omp-peer resolves a stale name or refuses naming the live agent | **Yes** | `test_peer.StaleNames` (4 tests: resolve, refuse with names, ambiguous, a send to the stale name delivered to the live agent and tagged), plus the live resolution above |

Suites: `python3 config/herdr/plugins/lifeview-fallback/test_lifeview.py` **102 OK** (95 before). `python3 config/herdr/skills/herdr-workstreams/test_peer.py` **17 OK** (13 before). I ran the lifeview suite three times in a row, because one new test was flaky at first (two turns in the same wall-clock second shared a session key). Each turn now gets its own key.

## Not done

- **Neither restart nor re-install.** You said you'd restart the daemon. omp-peer is installed by setup.sh, so I left it alone.
- **Cause 4** is the owner's call (above).
- **`[from:bro]` still cards.** Narrow it by adding `bro` to `COMMS_TAGS` if wanted.
- **Possible re-card after a restart:** `Harness.opened` and the session marker are in-memory only, and the hub drops `note`. After a restart, a turn that ended less than 2 minutes earlier, whose card is already `ready`, could open a second card, because `ready` no longer covers. That window is 2 minutes per restart, so I accepted it.

## Live delivery

The report path went to `omp-v25-wdp9`, the stale name, using the repo copy.
- omp-peer printed `omp-v25-wdp9 is stale (the pane rolled); its live agent is omp-v35-wdp9` and delivered.
- The coordinator's session file has exactly one entry with the path, tagged `[from:worker project:dotfiles id:claude-v2-wdpa]`.
- As before, the first Enter after the nvim paste was dropped and the existing retry submitted it.
