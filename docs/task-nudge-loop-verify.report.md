# Report: nudge-loop verification (docs/task-nudge-loop-verify.md)

Committed locally, not pushed. Files changed:
- `config/herdr/plugins/lifeview-fallback/lifeview.py`;
- `test_lifeview.py`;
- this report.

**To make it live:** restart the lifeview daemon.

## The finding

**No delivered nudge or tweak shape is misclassified, and the loop is not reproducing.** Every user-role entry prescient delivered, across all omp and claude transcripts, classifies `machinery` today and opens no card. The handoff's framing diagnosis does not match the data: no delivery in any transcript is wrapped in `<pasted_content>` or `auto:`.

Store state now (`prescient task list --json`): 323 items, **321 done / 1 ready / 1 queued**.
- **The one queued item** is the owner's own `auto: give me status on bro…` (origin owner, created today). It is not an echo.
- **0 items contain "is queued for".**
- **The 5 items containing "tweak sent"** are the 5 `auto: prescient: … tweak sent …` echo cards the spec names, all `done`, created 2026-11-02/03. That is before the `OMP_MACHINERY` work, and none since.

The tests did find two gaps, one of them in the reverse direction. Neither is in any transcript; both are below.

## 1. Every distinct shape, all transcripts

Method: lifeview's own `classify()` read every omp session transcript (1336 files) and every claude project transcript (1331 files). That is the same code path the daemon uses, so a "prompt" here is exactly what the classifier sees. Kept: user-role prompts containing `is queued for` or `tweak(s) sent`. Shapes are normalised as `tk-…`, `<project>` and `N`, and each is classified by `prompt_provenance`.

**Deliveries (prescient's own):**

| Shape (verbatim apart from the id, project and N) | omp | claude | Class |
|---|---|---|---|
| `prescient: task tk-… is queued for <project>'s coordinator - \`prescient task list --mine\` has it.` | 69 | – | machinery |
| `[from:harness project:prescient id:prescient-task-nudge]` ⏎ the same | 122 | – | machinery |
| `prescient: task tk-… is queued for <project>'s dev - …` (same tail) | – | 12 | machinery |
| `[from:harness project:prescient id:prescient-task-nudge]` ⏎ the dev form | – | 5 | machinery |
| `prescient: N tweak(s) sent from the life view - run \`.venv/bin/prescient tweak list\`, then follow the tweak routine in AGENTS.md.` | 21 (N=1) | 132 (N=1,2,3,4,6) | machinery |
| `[from:harness project:prescient id:prescient-tweak-doorbell]` ⏎ the tweak line | 4 | – | machinery |
| the tagged tweak delivered many times over into **one** entry, concatenated | 1 | – | machinery |

Every `prescient: ` user entry of any kind falls into the rows above, with one exception (below). The two templates are `tasks/store.py` `NUDGE` and `gantt/agent.py` `PROMPT`.

**Rows that only contain the string, not a delivery.** These are judged correctly:
- **omp, `owner` (7):**
  - two dispatches that quote the `NUDGE` template in their body (this task's own hand-offs);
  - four long pasted agent narratives;
  - **one splice:** `i had to ma` + the tweak doorbell + `nu`. The doorbell landed while the owner was typing, so the entry is the owner's own typing, and `owner` is right.
- **omp, `agent` (1):** a `From claude-…:` relay that mentions the doorbell.
- **claude:** 6 resume summaries (`machinery`). Also 22 claude-harness context entries (`<system-reminder>`, `<artifact-content…>`, `<pasted_content>`) that quote files containing the string. They classify `owner`. That is not a nudge shape, but harness-injected `<system-reminder>` entries reaching the classifier as prompts may deserve a separate look.

**The exception:** one untagged agent message addressed *to* prescient by name, `prescient: bro's voice session auto-restarted …` (2026-11-02, before tags). It is classified machinery, which is exactly the reverse case below.

## 2. What changed: two gaps the literal tests exposed

The tests the spec asks for were written first and run against HEAD's `lifeview.py`, in a temp copy. Plain and tagged literals passed. **19 subtests failed** in two places:

1. **Framed literals.** `<pasted_content id="x">` + a literal (same line, own line, with or without the close), `auto: ` + a literal, and `auto: <pasted_content …> ` + a literal all came out **owner**. `OMP_MACHINERY` is anchored on the raw prompt, so the harness wrappers that `WRAPPER` already strips for the tag hid it.
   - **Fix:** `framed_body()` strips the same leading `WRAPPER`, plus a trailing paste close, and `OMP_MACHINERY` matches against that. It equals the prompt whenever no wrapper leads it, so this is a strict superset: nothing that was machinery stops being machinery.
   - **Guard:** a paste followed by the sender's own words (`<pasted_content>…nudge…</pasted_content> why does this keep coming back?`) is *not* framing, so it stays the sender's (`owner`). This is tested.
2. **The reverse.** `prescient: why did the life view show bro twice?` came out **machinery, silently**, and so did the real agent message above.
   - **No rule is weakened.** The `prescient: ` catch-all stays machinery, so no unknown prescient delivery can ever restart the loop.
   - **What changed:** a `prescient: ` line that is not one of prescient's delivery shapes (`PRESCIENT_DELIVERY`) now emits `event machinery_unrecognized {"head": …, "why": "… tag it [from:owner]"}` to the daemon log, once per prompt head. So it is no longer silent.
   - **Explicitly marked owner text is owner:** `[from:owner …]` ⏎ `prescient: …` and `From the owner (prescient): prescient: …`. Both are asserted.

No other provenance rule changed. The tag rules, `MACHINERY_PROMPT`, `OWNER_MARKED`, `OMP_AGENT` and the autotask gates are untouched.

## For the coordinator: one decision, not taken

Should an *unmarked* owner line starting `prescient:` become `owner`? To do that, narrow the `prescient: ` branch of `OMP_MACHINERY` to `PRESCIENT_DELIVERY`.
- **The data supports it:** every delivery in every transcript matches `PRESCIENT_DELIVERY`, and recent deliveries carry `[from:harness]`, which beats shape anyway.
- **But** it narrows a provenance rule, and the spec forbids that. So it is your call, not mine. The `machinery_unrecognized` event shows how often it would matter.

## 3. Tests: `NudgeLiterals`, 5 tests

| Test | Asserts |
|---|---|
| `test_literals_are_machinery_and_never_card` | The literal strings copied from transcripts (both nudge targets, 1 and 2 tweaks, both tagged forms, the concatenated triple doorbell) are machinery. `autotask_check` refuses a card for a claude and for an omp. No `machinery_unrecognized` event fires for them. |
| `test_literals_behind_framing_are_machinery` | The nudge and the tweak behind each framing: paste on the same line, after a space, on its own line, each with and without the close; `auto: `; `auto: ` + paste; a `[from:harness]` line. All are machinery, with no card. |
| `test_a_paste_with_the_senders_own_words_after_it_is_theirs` | A paste followed by the owner's own words is owner. |
| `test_reverse_owner_text_starting_prescient_is_not_silently_machinery` | Tagged or marked owner text is owner. Unmarked text is machinery and reported once across 3 ticks. |
| `test_a_delivery_spliced_into_the_owners_typing_is_the_owners` | The real splice is owner. |

Suites: `test_lifeview.py` **122 OK** (117 before plus these 5). `test_peer.py` **17 OK**, untouched.

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | Table of every distinct nudge/tweak shape with its class | PASS. See section 1. Every delivery is machinery, and each non-machinery row is explained. |
| 2 | Tests with the literal strings, passing | PASS. `NudgeLiterals`, 5 tests. |
| 3 | The reverse is asserted | PASS. Marked owner text is owner; unmarked is no longer silent (the event). See the decision above. |
| 4 | If nothing is misclassified, say so and cite the store | PASS. No delivered shape is misclassified: 0 items contain "is queued for", the store is 321 done / 1 ready / 1 queued (the owner's own item), and the 5 tweak echoes are from 2026-11-02/03. |
| 5 | No provenance-rule change unless a misclassified shape is found | Only what the spec's own framed and reverse tests required. The machinery match now sees through wrappers, a strict superset, and the event is logging only. No rule was narrowed. |
