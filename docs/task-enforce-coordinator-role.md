# TASK: make the coordinator role actually binding in the config

The owner, 2026-11-09: *"You need to remember the development kind of structure, you
should be handing off work to Claude as much as possible because it is the expert on
the codebase and how to do stuff. Furthermore, you should be relying more on
sub-agents. So you are high-level coordination and communication, relying on
sub-agents to manage context, and Claude and its sub-agents are doing the actual
research or coding. Reconnect with this model, and if it's not enforced in the
dotfiles configuration, make it so."*

## Why he is saying it again

The rule **exists** in `config/omp/context-files/APPEND_SYSTEM.md`:

> "omp NEVER implements in its own session. Implementation goes to claude in the same
> project, or to @task subagents."

And I violated it all day: I edited `lifeview.py` directly for the auto-ready fixes,
the provenance classifier, the tag parser and the omp-coordinator gate. The owner had
to tell me twice — once earlier ("get Claude in on it because Claude is the
developer"), and again now.

So the problem is not that the rule is missing. It is that it is **not binding**:
one line in the middle of a preamble, contradicted by how the rest of the document
reads, and with nothing that makes violating it visible.

## What to change

**1. Make it a top-level, first-read rule, not a paragraph.**
Put the three roles in one block near the very top of `APPEND_SYSTEM.md`, phrased as a
chain of custody rather than a job description:

```
You are the COORDINATOR. You do not implement, research the codebase, or read bulk
files. You:
  - decide what should happen and why
  - write the spec (paths, change, acceptance) to a file
  - dispatch it to claude in this project, or to @task subagents
  - verify the result against the spec, and own the verdict
claude + its subagents are the ones who read, research, and write code.
Subagents exist so your context stays atomic: they return a compressed result,
never their working narrative.
```

**2. Name the violation explicitly.** The current text says what to do; it does not
say the failure is a *defect*. Add: *"Editing a repo file from your own session is a
process defect, even when it is one line and you are sure — the owner has had to say
this twice."* That is the sentence that would have stopped me.

**3. Make it observable, not just stated.** The rule is enforced only by memory today,
and memory failed. Options, cheapest first:
- a line in the **compaction brief** (`config/agents/compaction-brief.md`) — every
  compaction then re-states the role, which is exactly when an agent drifts;
- a **check script** beside `scripts/check-compaction-brief.py` style, e.g. fail if
  `APPEND_SYSTEM.md` loses the role block — the same shape as the brief checker, so a
  future edit cannot quietly delete it;
- if omp exposes a pre-tool hook that can see a file write in the session's own pane,
  prefer that. **Establish whether it exists before inventing anything.**

**4. Claude's side needs the mirror.** `config/claude/CLAUDE.md` already says claude is
the dev workhorse; make sure it also says the *positive* duty — claude does the
reading, research and coding, and delegates within itself via its own subagents for
atomic context. Otherwise the coordinator has nowhere to hand off to and the rule
collapses in practice.

## Acceptance

1. The role chain is in the first ~20 lines of `APPEND_SYSTEM.md`, as a block, in the
   coordinator/dispatch/verify shape above.
2. The explicit "editing a repo file from your own session is a process defect" line is
   present.
3. The role is re-stated in `config/agents/compaction-brief.md`, so a compaction
   restores it.
4. A check exists that fails if the role block is removed (same shape as
   `scripts/check-compaction-brief.py`), and it is wired where that one is.
5. `config/claude/CLAUDE.md` carries the mirroring duty for claude.
6. Nothing contradicts: grep the context files for any line implying the coordinator
   may implement, and fix it.
7. If a pre-tool hook could enforce this, report whether it exists — do not invent one.

## Note

This is instructions and checks only. Do not change how agents are spawned or how the
handoff works; the mechanism is fine, the discipline is not.
