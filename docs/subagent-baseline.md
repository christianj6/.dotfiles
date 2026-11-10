# Sub-agent delegation: the baseline, and how it gets measured

Owner's third ask: *"i feel like omp and claude agents arent relying on subagents as
much as i'd like."* He was right, and it is now measured rather than felt.

## The baseline (this session, the one that raised the complaint)

```
tool calls: 1961 bash+reads (779 read-like), 136 edit/write, 1 task
  -> delegation ratio 0.0%          (target >= 5%)
turns: 224; over threshold (>5 inline reads, no subagent): 44
BELOW TARGET
```

**44 turns read more than five files inline with no sub-agent.** One dispatch in 224
turns. That is the number the owner was describing.

Reproduce: `python3 ~/.dotfiles/scripts/check-delegation.py --omp` (or `--claude`).

## What changed, in three layers

**1. A trigger instead of a preference.** Both instruction files now say:

> **More than ~3 reads/searches to answer one question → stop and dispatch it.** If your
> first instinct is "I'll just read these files", that is the trigger.

with the brief template (`GOAL / WHERE / RULED OUT / RETURN` — compressed result only),
and the honest exception (1–3 known calls stay inline).

**2. The ratio is visible.** `scripts/check-delegation.py` measures dispatches against
all tool calls and lists the over-threshold turns. It is in the **compaction brief**, so
every compaction re-states the rule and the target — compaction is exactly when an
agent drifts back.

**3. The contradiction removed.** The old line *"for orientation you may read 1-2 key
files yourself"* sat three lines above the trigger with a different threshold, and was
read first. Deleted. There is now **one** reading-delegation threshold across both
files, and a grep proves it.

## Why this was needed three times

The rule existed all along ("delegate to subagents for atomic context"). It failed for
the same reason the coordinator role failed: **present, contradicted, unmeasured**. A
permissive line beside a rule wins, because it licenses the easy path and looks
legitimate. The fix each time was not more prose — it was removing the contradiction and
making the number visible.

## What a good ratio looks like

- **≥ 5%** of tool calls being dispatches — roughly one sub-agent per twenty calls;
- **0** turns with more than five inline reads and no sub-agent, or each one explained in
  that turn's report.

At the baseline that means going from 1 dispatch to roughly 100 across a session this
size. The target is deliberately modest: it is the difference between "once in 224 turns"
and "part of how work gets done".

## Not built, and why

omp's `tool_call` hook can only **block or rewrite input**; it cannot append context. A
hard block on the Nth read would be worked around, and rewriting input is too blunt.
`tool_result` *can* append — so a nudge ("you have read 4 files inline with no sub-agent;
dispatch the rest") is constructible, but it is the owner's call and is not built.
