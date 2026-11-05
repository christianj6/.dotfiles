# Delivery bug: an omp REPL nested in nvim is invisible to the box check

The owner had to press Enter by hand for a task nudged into my pane. Not a lost message — the text was typed and sat **unsubmitted in the input box**, while `_submit` reported "box looks submitted".

## Reproduction on the live screen

`_waiting()` decides whether the prompt is still in omp's box, and its box detector is:

```python
REPL_TOP = re.compile(r"╭── {1,2}\S[^╮]*─╮")
```

That matches a REPL running **standalone**. Inside nvim's `:terminal` the REPL's borders are shifted right by nvim's own window border, so the real top line reads:

```
                     │╭───────────────────────────────────────────────
                      ^ nvim's border, then the REPL's corner
```

Measured on pane `wD:p9` (my own, omp inside nvim):

```
nested tops found: 3
REPL_TOP matches plain tops: 1        # a STALE one, further up
a nested top is a plain top?: False
```

So `_waiting` picks the **last plain match** — which is not the live box — extracts one line, hits `│╰─`, and returns `False` (= "not waiting" = submitted). `_submit` then returns `"box"`, `_deliver` says *"the box looks submitted; no transcript shows it"*, verdict `pending`. The text stayed in the box until the owner pressed Enter.

That also explains why the verdict was `pending` rather than a lie: the transcript never showed it, so the honest branch fired. The **screen check** is what's wrong, and it is the thing whose whole job is "never trust the box alone" — it trusted a box that wasn't there.

## Voltage

This is the "typed but not submitted" class from the `83173fa`-era work, inverted: previously the check *false-positived* a failure when the text had landed; now it *false-negates* and leaves a real message unsubmitted. Both come from the same place — the box detector assuming one layout.

Embedded-nvim is the normal case for every omp pane in this workspace, so this affects **every** omp target, not an edge case. It is why `--explain` and the tray have been working (HTTP + GET) while *nudges* needed a human.

## The fix

Match the top border whether or not a host pane's border prefixes it, and require the box to be the **live** one:

```python
REPL_TOP = re.compile(r"(?:│\s*)?╭─{2,} {0,2}\S[^╮]*─╮")     # nested (│╭──) or standalone (╭──)
```

and in `_waiting`, bottom-border detection should accept the same nesting:

```python
if re.search(r"(?:│\s*)?╰─", ln):
```

Two further hardening points, because "one stale top matched" is the actual trap:

1. **Take the LAST top match and require that a bottom border follows it.** If no bottom is found, return `None` ("box not on screen") rather than `False` — `None` already means "no blind Enter", which is the safe verdict, and `False` is the one that lies.
2. A regression test built from the **real captured screen** (nested borders), not a hand-written standalone one. The existing tests evidently use the standalone shape, which is why this passed.

## Verify

1. `_waiting(nested_screen, needle_with_text_in_box)` is `True`; after the text leaves the box, `False`.
2. On a screen where the box cannot be found at all, `None` (never `False`).
3. Live: nudge an omp pane in nvim with a fresh task — the transcript shows the text as a user entry, verdict `ok`, no human Enter.
4. The owner's case end to end: `prescient task add` against a working omp pane lands without manual Enter.

## Note on scope

This is prescient's file (`prescient/gantt/agent.py`), so it is the coordinator's to fix, not mine. Filed with the reproduction because "the box looks submitted" is a claim that needs a screen to argue with.
