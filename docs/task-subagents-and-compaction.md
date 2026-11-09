# TASK: two asks — more sub-agent work, and proactive compaction

Owner, two separate ideas (both captured as `tk-09e43448c80b`, `tk-13ee9d2f08f9`):

1. *"encouraging both OMP and Claude sessions to do more of their work in sub agents so that we have more kind of like atomic context management"*
2. *"have the agents do compaction a bit more proactively so not like when we're at ninety percent full"*

The owner supplied the model for what a compaction should produce. That is the
specification for #2, quoted:

> **Compact instructions**
> Write a handoff brief for the remaining work, not a history. Include:
> 1. The original task, near-verbatim.
> 2. Current step and the immediate next action.
> 3. Remaining plan in order, and the "done" criteria.
> 4. Changed files with exact paths and whether each change is verified.
> 5. Failed approaches not to repeat.

## What exists today (measured)

- **Sub-agents**: `APPEND_SYSTEM.md` already says coordinators dispatch implementation to claude or `@task` subagents, and a spawned subagent must not delegate further. So the *rule* exists — what is missing is anything that makes it happen in practice for **Claude** panes, which have no equivalent instruction.
- **Compaction**: there is **no compaction configuration at all**. `config/omp/config.yml` has no compaction key (keys are providers, modelRoles, theme, advisor, prewalk, memory, cycleOrder, statusLine, display, dev, browser), and no context-file tells an agent how to compact or when. `preset: compact` at line 53 is the **status line**, not context compaction — a trap for the next reader.

## Idea 1 — atomic context by delegation

The mechanism should be *structural*, not exhortation. Two concrete pieces:

**a) A sub-agent default in the instructions.** For both omp and Claude:
- multi-file or multi-step work → dispatch to a sub-agent with a self-contained brief,
  so the parent's context holds the *outcome* rather than the transcript of the work;
- the sub-agent returns a compressed result (what changed, what was verified), never
  its working narrative — that is the "atomic" part: the parent's context grows by a
  summary, not by the exploration.
- **Explore/read-heavy work is the best candidate**: bulk reading is what burns context
  and what compresses most cleanly.

**b) Claude needs the equivalent instruction.** It has none today; omp does. Claude's
`CLAUDE.md`/settings should carry the same rule or the two panes will behave
differently — which is the asymmetry the owner keeps spotting.

## Idea 2 — proactive compaction

Adopt the owner's brief as the compaction artifact, and compact **before** 90%.

- **What**: the five-item brief above. It is a handoff, not a history — which is
  exactly what a good compaction is, and it is better than whatever summarisation
  happens today because it is written for the *next* agent rather than about the past.
- **When**: a threshold well below 90% (a two-thirds budget leaves room to finish the
  current step after compacting, which 90% does not), **and** at natural boundaries —
  after a verified unit of work, before a dispatch, at a session checkpoint. Compacting
  mid-step is what loses the thread.
- **Where**: omp has no config key for the threshold today. Whoever implements this must
  first establish whether omp exposes one (a setting, an extension hook, or an env var).
  If it does not, the honest fallback is an instruction-level rule ("at ~2/3, write the
  brief, then compact") plus a hook if one exists — **not** an invention of a config key
  that does nothing.

## Order of work

1. **Establish the mechanism for compaction** (does omp expose a threshold/hook?). Without
   that answer, #2 is a wish. Report the finding before writing any config.
2. Compaction brief: put the owner's five items into the context files, so any compaction
   — proactive or forced — produces a handoff.
3. Sub-agent rule in both `APPEND_SYSTEM.md` and Claude's instructions, with the
   "return a compressed result, never the narrative" clause.
4. Only then consider tuning thresholds.

## Acceptance

1. The compaction brief (all five items, near-verbatim to the owner's text) is present in
   the context files, and a test or check shows it is loaded.
2. A written answer to "does omp expose a compaction threshold or hook, and how" — with
   the source of the answer, not an assumption.
3. The sub-agent rule exists for **both** omp and Claude, and they do not contradict each
   other.
4. `config/omp/config.yml` is not given a key that nothing reads — if there is no
   threshold setting, say so and put the rule in the instructions instead.
5. Nothing here changes behaviour for a subagent told not to delegate further.

## Note

These are two independent changes; land them as two commits. #1 is instructions only;
#2 needs the mechanism question answered first.
