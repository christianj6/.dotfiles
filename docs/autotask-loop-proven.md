# The auto-task loop: PROVEN end to end (2026-11-13)

Reported by heinzel's coordinator, and **I verified it independently** rather than accepting the
report — because the previous "pass" was a false one (it cited my own probe as its own card).

## The proof

An **ordinary work turn** on a non-dotfiles pane — the coordinator dispatching a fix brief to its
Claude — created its own card:

```
tk-81b913b14ae0  project=heinzel  origin=owner  state=queued  created 2026-11-13T18:43:23
                 "auto: give it to claude"
```

and `--explain` for `omp-v36-w5p1d`, checked by me:

```
auto-task: covered by tk-81b913b14ae0 (queued)
open: ok tk-81b913b14ae0  (59s ago, 'auto: give it to claude')
```

Same id, that turn's timestamp, and the coordinator did not file it.

## Why this counts as proof and the earlier one did not

There are now **two independent observations**:

| | card | how it was created | independent? |
|---|---|---|---|
| 2026-11-12 | `tk-03633b4a4f71` | my own ordinary work turn, `origin: harness` | yes — mine |
| 2026-11-13 | `tk-81b913b14ae0` | heinzel's ordinary work turn, `origin: owner` | **yes — a different project's pane** |

The false pass was `tk-5441ae6cc5ec`, which was **my probe**, read by the coordinator as its own
card. The difference is not the code path — it is that a witness who can distinguish the id from
a decoy has now confirmed it, twice, on two panes and two projects.

The title is also the right evidence: *"give it to claude"* is the **owner's** phrasing, so the
card came from the turn's prompt rather than from anything the agent wrote about itself.

## What the fix chain was, for the record

Four separate causes, each alone sufficient (see `docs/echo-closed.md`), plus the write path:

1. coverage was agent-keyed while hub items carry `agent: null` → `covering_items`, project-keyed
2. the daemon predated the parser → restart
3. the tag parser was anchored, so a same-line wrapper defeated it → search the first line
4. the wrapper was on its own line, so the tag sat on line 2 → strip wrappers, then anchor
5. **and the writes were 403'ing** — the hub's new launch token was never sent by the plugin, so
   every card silently failed. That one meant "detected but never opened" until `X-Prescient-Token`
   was sent.

## The diagnostic improvement that made this checkable

`--explain` now prints both halves:

```
auto-task: covered by <id> (state)          <- a turn already covered is stated, not silent
open: ok <id> (Ns ago, '<title>')           <- the last open attempt, named
```

Both lines are what let the coordinator prove its own case and let me check it. Before, the
`auto-task:` line printed only the *why* string, which read like a decision without being one.
