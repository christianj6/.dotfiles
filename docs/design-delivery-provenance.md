# Design: provenance must be recorded at delivery, not guessed later

The owner, twice: *"Things should be tracked no matter where I put them in"* and *"I want a full task lifecycle even if something isn't created through Prescient… Distinguishing between a task that I'm giving it and you know, just communication from other coordinators."*

I implemented a prompt-shape classifier. It is not enough, and I can now show why.

## The proof that shape-classification cannot work

I dispatched a task to dotfiles' Claude through herdr. The harness immediately recorded it as:

```
tk-35a1ddfb2295 | origin=owner | auto: Read /Users/.../task-autotask-owner-lifecycle.md and implement it...
```

**Wrong.** That was *my* message — a coordinator handing work to a worker — recorded as the owner's. The classifier saw a human-sounding sentence and said `owner`.

Then I checked what the receiving side actually knows. A user message in Claude's transcript is:

```json
{"content": "...", "role": "user"}
```

**No sender. No metadata. Nothing.** Every delivery path — the owner typing, bro, prescient's `agent._deliver`, `herdr agent prompt`, a coordinator's dispatch — produces an identical entry. `omp-peer`, herdr and prescient all type into the same box.

So the question "did the owner ask this or did an agent?" is **unanswerable from the transcript**, at any level of cleverness. My classifier was inferring a fact that had been erased before it could be read.

## The fix: record the sender when it is known

Provenance is known exactly once — **at delivery**. Prescient's `agent._deliver(target, text)` knows who is asking. Today it logs nothing.

### 1. Prescient records every delivery

A `deliveries` table (or the existing event log): `(at, target_agent, target_project, text_digest, by, source)` where `by ∈ owner | agent | harness | bro` and `source` names the caller (e.g. `omp-v35-wdp9`, `bro`, `prescient task add`). One row per delivery, written whether or not it succeeds — a failed delivery is still provenance.

### 2. The harness attributes a turn by matching it to a delivery

When auto-task considers a turn, it has the prompt text and a timestamp. Look up the delivery:

- **exact match** on the prompt's leading text within a window → that delivery's `by` is the turn's origin;
- **no match** → the prompt arrived by a path nothing recorded (the owner typing, a paste, a resume) → `origin: owner` is the safe reading, because an unrecorded delivery is overwhelmingly the human;
- **machinery shapes** (`<task-notification>`, continuation summary, bare `[Image:]`) still refused first — they never become cards regardless of sender.

This inverts the current logic: instead of guessing from prose, ask the system that handed the text over. The classifier becomes the **fallback for unmatched prompts**, not the primary rule.

### 3. Keep it one rule, one place

The lookup lives beside `open_task`, the only place a card is created. Nothing downstream re-derives provenance — the existing rule stands, the *source* changes.

## Why this is the right shape

- **It cannot be spoofed by phrasing.** A coordinator's request worded like the owner's is still `agent`, because the delivery says so.
- **It fails closed in the safe direction.** No record → `owner` → the work is carded and the owner sees it. The alternative (default `harness`) hides real requests, which is today's bug.
- **It needs no change to the agents.** herdr, omp-peer and the panes keep working exactly as they do.
- **It makes the tray honest.** `origin: agent` cards rank below working; `origin: owner` cards earn green. Both are now true rather than guessed.

## Acceptance

1. `prescient` records a delivery for every `_deliver` call, with `by` and `source`, success or failure.
2. A coordinator's dispatch to a worker → the resulting card is `origin: agent`, **never** `owner` (this is `tk-35a1ddfb2295` reproduced and shown fixed).
3. The owner typing in a pane → `origin: owner`.
4. An unmatched prompt with no delivery record → `origin: owner` (fail safe), and it is logged as unmatched so the gap is visible.
5. Machinery shapes still produce no card at all.
6. The **full lifecycle** for a harness-created card with nothing pre-created in prescient: `queued → working → ready`, and `project_icon` → `ready`.
7. A one-tool-call owner request counts as work (the `WORK_MIN_TOOL_CALLS` gate must not apply to attributed owner/agent turns).

## Scope

Item 1 and 2 are prescient (the hub owns the record). Items 2–7 are the dotfiles plugin. Both are needed before the lifecycle is trustworthy; neither alone is enough.

## What I got wrong, for the record

I shipped a prompt-shape classifier and reported it as the fix. It was a plausible heuristic over data that had already lost the answer. The measurement that exposed it was dispatching a task and watching the harness label my own message `owner` — the test I should have run before writing the classifier.
