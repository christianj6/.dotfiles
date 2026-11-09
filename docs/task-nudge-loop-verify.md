# TASK: verify the nudge loop is fixed, with the literal strings as tests

From bro's coordinator: `docs/self-improvement/66b-handoff-dotfiles.md` in the bro repo (read in full).
Owner's words: *"stop that phantom card from reappearing, that is annoying."*

## What I measured, which changes the diagnosis

The handoff predicts the cause is **framing** — that the text reaching the transcript is
wrapped, so `OMP_MACHINERY`'s `^\s*` anchor misses `prescient: `. I checked the actual
transcript entries. **They are not wrapped.** From my own pane
(`-.dotfiles/2026-10-03T03-42-34-…jsonl`), 29 user-role nudges, all of this exact shape:

```
prescient: task tk-521d85e1842a is queued for dotfiles's coordinator - `prescient task list --mine` has it.
```

Position 0, no prefix, no `<pasted_content>`, no `auto:`, no tag. And the classifier
already handles it:

```
OMP_MACHINERY.match(literal) -> True
prompt_provenance({prompt: literal}) -> "machinery"
autotask_check(same) -> None | "this turn is about the task system itself …"
```

So **framing is not the cause, and the classifier is not failing.** The loop as described
is also not reproducing now: zero items contain "is queued for", and the store is
`319 done / 1 ready / 0 queued`.

## What the historical echo actually was — a DIFFERENT message

The only nudge-echo cards in the whole hub are five, all of the shape:

```
auto: prescient: 1 tweak sent from the life view - run `.venv/bin/prescient tweaks show` …
```

That is the **tweak notice**, not the `task … is queued for` nudge the handoff describes,
and all five predate the `OMP_MACHINERY` work (2026-11-02/03). They are not recurring.

So there are three candidate stories and only measurement can separate them:
1. the loop is already fixed and the handoff describes a stale observation;
2. it recurs only under a shape nobody has captured yet;
3. it is real but in a path I have not exercised (a different pane, a different store).

## What to do — prove or disprove, then lock it in

1. **Print every distinct user-role entry containing `is queued for` or `tweak sent` across
   ALL transcripts under `~/.omp/agent/sessions/`** — not just one pane's. Report the
   distinct shapes verbatim, with counts. If any shape is NOT classified `machinery`, that
   is the bug and it gets fixed; if every shape IS, say so plainly.
2. **Add tests with those literal strings** — exactly as the handoff asks, because the
   literal is the thing that must never regress:
   - `prescient: task tk-… is queued for …'s coordinator - \`prescient task list --mine\` has it.` → machinery
   - `prescient: 1 tweak sent from the life view - …` → machinery
   - the same two with the harness framing in front (`<pasted_content id="x">`, `auto: `,
     a `[from:harness …]` line) → machinery
   - **the reverse**: an owner sentence that merely *starts* with "prescient:" →
     owner, or at minimum not silently carded as machinery.
3. **Report the counts.** If the loop is not reproducing, that is the finding and it must
   be stated — do not implement a fix for a bug that measurement cannot show.

## Acceptance

1. A table of every distinct nudge/tweak user-role shape found across all transcripts, with
   its classification. Any non-`machinery` row is either fixed or explained.
2. Tests containing the **literal** strings above, passing.
3. The reverse case asserted: owner text starting with "prescient:" is not machinery.
4. If no shape is currently misclassified, the report says so explicitly and cites the
   store state (`0 queued`, `0` items containing "is queued for") as the evidence.
5. No change to the provenance rules themselves unless a misclassified shape is found.

## Note

The prescient half (do not nudge a target that is transitioning its own item) removes the
loop at the source and is going to prescient's coordinator separately. This task is the
classifier plus the proof. **Do not weaken any existing provenance rule to make a test
pass** — if the literal is already machinery, the value here is the regression test, not a
change.
