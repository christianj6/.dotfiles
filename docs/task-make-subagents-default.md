# TASK: make sub-agents the default, not an aspiration

Owner, third time of asking: *"i feel like omp and claude agents arent relying on
subagents as much as i'd like."*

## Measured — he is right, and the numbers are the argument

Tool calls in a live session, by kind:

| agent | bash/Bash | Edit+Write | Task/Agent |
|---|---|---|---|
| omp (coordinator) | **2103** | 206 | **2** |
| claude (workhorse) | 579 | 141 | **0 seen** |

Both configs already say "delegate to subagents for atomic context". Both agents
almost never do. **The instruction is present and not binding** — the same failure as
the coordinator role, which the owner also had to repeat twice. Prose in a preamble
loses every time to the path of least resistance.

## Why prose fails here, specifically

- "Prefer subagents for multi-file work" has no threshold, so nothing is ever over it.
- The parent *can* do the work itself, so it does — reading and editing inline is
  immediate, while delegating costs a round trip and a written brief.
- Nothing observes the ratio, so drift is invisible. An agent cannot notice it is
  inlining what it should be delegating.

## What actually changes behaviour — three layers, cheapest first

**1. A concrete, checkable trigger (in both agent instruction files).**
Replace "prefer" with a rule an agent can apply without judgment:

> Before any **read-heavy or multi-file exploration**, count the calls you are about to
> make. If it is **more than ~3 reads/searches to answer one question**, stop and
> dispatch it to a subagent with a self-contained brief. Bulk reading is what burns
> context and what compresses most cleanly — that is the whole point.

> If your first instinct is "I'll just read these files", that is the trigger.

Give the exact brief shape too, so there is no design cost at the moment of decision:
goal, where to look, what is ruled out, what to return (compressed result, exact paths,
what verified, what is open — never the narrative).

**2. Make the cost visible: a per-session ratio.**
Add a small check script (the `check-*.py` pattern already in `scripts/`) that reads a
session transcript and prints:

```
tool calls: 2103 bash, 206 edit/write, 2 task   -> delegation ratio 0.1%
```

Run it as an **end-of-turn self-check** for both agents — "if this turn had >5 reads and
no subagent, say why in the report". Cheap, and it turns an invisible habit into a
number the agent sees.

**3. Structural, if it exists: a hook that can refuse.**
The worker established that **omp has a blocking `tool_call` hook** (the same one that
could refuse a coordinator file-edit). Use it — conditionally and narrowly:
- **not** a hard block (that would break legitimate inline work and drive agents to
  work around it);
- **a nudge on the Nth read in a turn** with no subagent yet: allow the call, but append
  a context line ("you have read 4 files inline this turn with no subagent; dispatch the
  rest"), the same shape as omp's `avoid_claim` retry line.
Establish whether the hook can inject context versus only block; report which.

## Acceptance

1. Both instruction files carry the **threshold rule** ("more than ~3 reads to answer one
   question → dispatch") and the **brief template**, phrased as a trigger, not a
   preference. A grep shows the words "prefer"/"consider" are gone from the delegation
   section.
2. `scripts/` has the ratio checker; running it on a real transcript prints the counts
   and the ratio (verify against a known session).
3. The ratio appears in the **compaction brief**, so every compaction re-states it.
4. A report on whether the `tool_call` hook can inject context or only block, with the
   source of that answer — and **no hook is built** without the owner's say-so.
5. A before/after: run the checker on the current session now (the 2103/206/2 one) and
   state what a "good" ratio would look like, so "more" is measurable rather than a
   feeling.
6. Nothing here forbids inline work for a small, known lookup — the rule is a threshold,
   not a ban.

## Note

This is the third ask; treat the instruction change as insufficient on its own. The
measurement (item 5) and the visible ratio (items 2–3) are what make it stick, because
they are the only parts an agent cannot ignore by forgetting.
