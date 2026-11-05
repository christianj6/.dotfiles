# Report: owner lifecycle with nothing pre-created (task-autotask-owner-lifecycle.md)

Owner's requirement: *"I want a full task lifecycle even if something isn't created through Prescient … Distinguishing between a task that I'm giving it and … just communication from other coordinators."*

Files changed: `config/herdr/plugins/lifeview-fallback/lifeview.py` and `test_lifeview.py` (the two the spec names), plus this report. Committed locally, not pushed.

## Read this first: the reproduced case had TWO gates, and this change opens one

I replayed the exact turn from bro's transcript: the prompt "Can you check the current git branch…", 1 tool call, a 6.3 s span, provenance `owner`. It went into **bro's omp pane** (wD:p5), and `autotask_check` refused it at an earlier gate than the spec names:

```
as the real pane (omp)  -> "this agent coordinates; its work is other agents' tasks, not its own card"
same turn as a claude   -> before: "trivial so far: 1 tool call(s), 6s"   after: card "work session: 1 tool calls, 6s"
```

The spec's diagnostic line ("not working, and no turn ended in the last 2 min") came from the first gate of all: the check ran more than 2 minutes after the turn ended.

**The fix below makes the lifecycle work for owner requests in a Claude pane. It does NOT make a card for an owner request typed into an omp pane.** I deliberately left the coordinator gate closed, for the reason in the next section.

## Why the omp gate stays closed (evidence)

I classified every prompt in the live omp transcripts with the current `prompt_provenance`. Every entry carries `attribution: "user"`, and `steering` only means "typed while busy", so text shape is the only signal. On omp panes it calls most coordinator traffic `owner`:

- hub nudges: `prescient: task tk-… is queued for …'s coordinator` (8–25 per pane);
- tweak notices: `prescient: 1 tweak sent from the life view`;
- relays from other agents: `From claude-prescient: …`, `bro request tr-…` (76 on bro's omp);
- free-form worker reports: "Both landed here too: 1f2c25e …", "WAVE 5b done -> …", "REPORT …", "Card 01 … landed".

Opening the gate for `owner` turns would turn those into owner cards. The hub nudges would bring back the 2026-11-03 self-referential loop, since every card nudges the omp, whose next turn would card the nudge. That is the very confusion the owner asked to avoid.

A follow-up could open it safely. Classify the known omp comms shapes as not-owner:
- `prescient:` as machinery;
- `bro request tr-` as machinery;
- `From claude-…` / `Task from the … coordinator` as agent;
- keep `From the owner, via bro` as owner.

Free-form worker reports have no marker, though. Separating them needs a sender marker: for example, `omp-peer send` could prefix its messages, which would be a dotfiles change. That is a design decision for the owner and coordinator, not something to guess.

## What changed

1. **The threshold no longer gates owner/agent requests** (`autotask_check`). This is the spec's rule verbatim: `trivial and not (origin in ("owner", "agent") and calls >= 1)`. `WORK_MIN_TOOL_CALLS` stays 2, and a test pins that.

   Note: every turn that reaches this gate is already `owner` or `agent` (machinery and unattributed turns are refused before it). So in effect the gate is now "at least one tool call". The threshold still applies in full to any other provenance class, and the tests pin that too.
2. **The card's text is what was asked.** For an owner or agent origin, `hub_open_task` sends `auto: <the prompt>` as the hub card's `text`, not the agent's reply. The title `autotask_check` returns (used in logs and by the bro path) is unchanged, so its existing tests stand.
3. **A chain break for exactly this case.** A 6 s turn ends between the plugin's 10 s ticks, so the harness opens the card *after* the answer. Auto-ready's guard ("no answer since the task was handed over") then blocked it forever.

   The old escape was a session marker in the creation note, but the hub drops `note` on create. Now the harness remembers the session each card was opened for (`Harness.opened`, re-attached each tick by `annotate()`), and `task_at` uses it while the item is still `queued`, which is the same "nobody moved it since" rule as before.

   This memory is in-process only: after a daemon restart, such a card waits for the agent's own `ready`.
4. `hub_open_task` takes the project `World` already stamped on the agent, by the same rule as `project_name`.

## Lifecycle observed (acceptance 1–2, `OwnerLifecycle.test_1_2_…`)

This runs the real `Harness.auto_task` and `auto_ready` in `tick()`'s order, against a fake hub that enforces the hub's rules:
- `create` queues at once;
- `start` only from queued;
- `ready` only from working;
- `by` must be a role.

It uses a two-tick clock, a Claude workhorse pane plus its omp, and the hub starts with **no items**.

```
lifecycle (auto-created only): created (by owner) -> queued (by owner) -> working (by harness) -> ready (by harness); rings per tick: ['queued', 'ready']
```

- Hub calls, asserted in order: `create(origin=owner)`, `start(by harness)`, `ready(by harness)`.
- Tick 1 opens the card 20 s after the answer, and the ring is amber (`queued`). Tick 2 (70 s later) marks it ready, and `project_icon` gives `ready`.
- The card's `origin` is `owner`. Its `text` is `auto: Can you check the current git branch in the bro repo and tell me what it is? Just run the command.` (snippet-trimmed). Its summary is the agent's answer.

## Both provenance cases

| Case | Prompt | Card | Ring |
|---|---|---|---|
| owner (test_1_2) | the owner's git-branch request, 1 tool call | `origin: owner`, reaches `ready` | **ready** (green) |
| agent (test_3) | `Round 7: docs/specs/round-7.md - fix the parser`, 1 tool call | `origin: agent`, reaches `ready` | **working**: an agent card never turns the ring green |
| machinery (test_4) | `<task-notification> …`, 3 tool calls | none, and no hub call | – |
| conversational (test_5) | a question, 0 tool calls | none, and no hub call | idle |

## Test changes (no assertion weakened)

- `test_threshold_blocks_trivial_turns` and `test_turn_that_just_ended_still_gets_its_task` asserted that a one-call `owner` turn is trivial, which is exactly the rule the spec reverses. Their threshold and span assertions are kept, now against a non-owner/agent provenance class, where the threshold still holds.
- New `test_owner_or_agent_one_call_request_is_work` covers the reversed case, and also a zero-call turn and `WORK_MIN_TOOL_CALLS == 2`.
- New `OwnerLifecycle` (4 tests) and its `LifecycleHub` fake.
- Result: `python3 config/herdr/plugins/lifeview-fallback/test_lifeview.py` gives **87 tests, OK** (82 before).

## Not done, and why

- **The omp-pane owner request:** see above. It needs a sender marker or the owner's call on comms shapes.
- **A pre-existing bug, found while building the fixture:** `scan_turn` and `scan_tail` never read a transcript's **first line**. When the backwards read reaches offset 0, the leftover `carry` is dropped. Real transcripts start with a bookkeeping entry, so live it is harmless. I left it unfixed (outside this spec), and the fixture has a header line with a comment saying why.
- **Covering is still agent-keyed:** `tasks_of` and `COVERING` use bro vocabulary. A second owner request in the same pane while a card is open opens a second card, and then auto-ready reports "ambiguous". Also outside this spec.
- **The live daemon wasn't restarted;** the change takes effect at its next restart.
