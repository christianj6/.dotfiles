# The echo is closed — four causes, all fixed and verified

Owner: *"this seems like our recent work misbehaving as a kind of echo. figure out the cause."*

It was four independent causes wearing one symptom. Each alone reproduced it, which
is why fixing them one at a time kept it alive — and why I reported it fixed four
times before it was.

| # | Cause | Fix |
|---|---|---|
| 1 | auto-task's coverage check was **agent-keyed** (`tasks_of`) while hub items carry `agent: null` → `covering` always empty, so a worker with an open item opened another card every turn | `covering_items()`, project-keyed (`227c083`) |
| 2 | the lifeview **daemon predated the tag parser** (started 18:44, parser landed 19:51) | restarted |
| 3 | the tag parser was **anchored** `^\s*\[from:`, so a same-line harness wrapper defeated it | search the first line (`e3f9c9f`) |
| 4 | the harness wrapper is on **its own line**, so the tag lands on line 2 — which my own "first line only" guard refused to look at | strip known wrappers, then anchor (`d902db5`) |

## Verified after the final fix

```
baseline 290 items -> 291, and the one new card was project=bro about turn-taking
                     (a real owner request, not an echo)
items matching "echo probe D":  0
prescient-project cards since the restart:  0
items containing "[from:" created since:    0
```

The five shapes the parser must handle, all correct:

| Prompt | Verdict |
|---|---|
| `<pasted_content id="x"> [from:coordinator …] t` | agent |
| `<pasted_content id="x">` ⏎ `[from:coordinator …] t` | agent |
| `auto: [from:owner …] t` | owner |
| `here is a log:` ⏎ `[from:harness …] t` | **owner** — a quoted tag never re-attributes |
| `[from:owner] plain` | owner |

117 plugin tests, plus the peer and prescient suites, all green.

## Why my testing missed cause 4

My own pane's prompts are already tag-first, so every test I ran there **could not
fail**. The wrapper only appears on prescient's pane. I tested the fix where it
worked and reported it fixed — the same "function checked, system inferred" mistake
the `fixed-claim-call-sites` rule exists to prevent, committed while holding the rule.

The check that would have caught it: run the reproduction against the pane that
actually exhibits the bug, not the one that's convenient.

## What is now true

- An agent-to-agent message **never** cards: `[from:coordinator]` / `[from:worker]`
  are comms by definition, so a coordinator's dispatch cannot become a task about itself.
- A worker with an open item in its project does not open another.
- A tagged message is read as its sender, whatever wrapper precedes it — and a tag
  quoted mid-text is ignored and logged.
- The owner's own words still card and still complete the lifecycle.
