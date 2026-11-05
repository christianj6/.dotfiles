# Design: telling the owner's work apart from agent chatter

The owner's concern, in his words: *"bc claude uses the chat input to send messages to the coordinator there is risk of confusion on what is a real 'task' from me and what is just comms."*

He is right, and the risk is concrete: **auto-task opens a card for any turn with enough tool calls** (`calls >= 2`, or 1 call spanning > X). It does not know who asked. So coordinator chatter in a pane — "round 25 done, moving to the balcony", "here's the trace", an agent nudging its own worker — becomes a hub task indistinguishable from work the owner asked for. The owner then sees cards he never asked for and cannot tell which are his.

## What the data says (measured on heinzel's live transcript, 65 user-role entries)

| Kind of prompt | Count |
|---|---|
| `Round N: …` (a spec handed to the worker) | 19 |
| `<task-notification>` (the harness's own plumbing) | 16 |
| `[Image: …]` (a pasted screenshot) | 11 |
| other / free prose | 12 |
| continuation summary (context ran out) | 6 |
| `Discussion…` / spec path | 1 |

**Two of these are not work at all** and auto-task treats them identically:
- `<task-notification>` — pure machinery. 16 of 65. Must **never** become a card.
- continuation summary — the harness resuming, not the owner speaking. Must never become a card.

And the rest is genuinely ambiguous between "the owner asked for this" and "an agent was handed this".

## The solution: `origin`, not heuristics

The hub **already** carries `origin` (`owner | agent | harness | bro`) on every item, and it is shown in the tray. That is the right axis — the question "is this from me or from an agent" is *exactly* what `origin` means. The bug is not that the concept is missing; it is that **auto-task always stamps `origin: harness`** regardless of whose words started the turn.

So:

### 1. Classify the turn's *provenance*, at creation

Auto-task already reads the prompt (`scan_turn`). Classify it there, cheaply and conservatively:

| Prompt shape | Who asked | Card |
|---|---|---|
| `<task-notification>`, continuation summary, `[Image: …]` alone | **machinery** | **no card, ever** |
| starts with an agent's own hand-off idiom (`Round N:`, `Spec:`, a path to a spec the agent wrote) | **agent** | card, `origin: agent` |
| anything else — a human sentence | **owner** | card, `origin: owner` |

The first row is the important safety rule: **machinery never becomes tracked work**. That alone removes 22 of 65 turns in the sample from candidacy.

The middle row uses the fact that this project *already* has a convention: rounds arrive as `Round N: …` with a spec path. The agent names it in the prompt, so the evidence is in the text, not guessed.

### 2. Make the distinction visible where the decision is made

- **`origin` on the card** — already exists, now actually correct. `owner` cards are the owner's; `agent` cards are work an agent started on its own initiative.
- **The tray and the icon rank them differently.** An `owner` card that goes ready is the thing that deserves green. An `agent` card going ready is progress, not a request for the owner's verdict — otherwise a busy agent floods him with "ready for your verdict" for work nobody asked him about.
- **`why` says it in words**: "a task you asked for is ready" vs "an agent finished a task it started".

### 3. One rule, one place

`origin` must be stamped **where the card is created**, from the turn's provenance — not re-derived later by any consumer. A consumer that guesses provenance from text is the same class of bug as the agent-keyed auto-ready: a second, weaker copy of a rule that already exists.

## What this deliberately does NOT do

- **It does not try to detect "comms" by content.** "That's annoying" and "fix the z-fighting" are both short human sentences; classifying by phrasing is what produced the `which_kind` mislabels. Provenance is structural: who put the text there.
- **It does not suppress agent cards.** Work an agent started should still be tracked — the owner said "things should be tracked no matter where I put them in". The fix is to *label* it, not to hide it.
- **It does not change auto-ready's guards.** Settled, no-other-agent-busy, finished-answer, started-by-the-agent all stay.

## Acceptance

1. A `<task-notification>`-only turn opens **no** card (test with the real notification text from the transcript).
2. A continuation-summary turn opens **no** card.
3. A `Round N: …` turn opens a card with `origin: agent`.
4. A human sentence ("fix the z-edge, it still flickers") opens a card with `origin: owner`.
5. An `owner` card that goes `ready` ranks above an `agent` card that goes `ready` (the owner's attention is the scarce thing).
6. The `why` line distinguishes the two in words.
7. Existing owner-created and bro-created items keep their `origin` — nothing is retroactively relabelled.

## The residual risk, stated

Provenance is inferred from the prompt's *shape*, and a determined caller could imitate a human sentence. That is acceptable: this is a labelling question, not a security boundary, and the failure mode is a mislabelled card rather than a lost task. What is **not** acceptable is the current state, where every card claims `origin: harness` and the question cannot be asked at all.
