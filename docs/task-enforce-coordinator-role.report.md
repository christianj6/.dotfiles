# Report: make the coordinator role binding (docs/task-enforce-coordinator-role.md)

Committed locally, not pushed. This change is instructions and checks only. Spawning and handoff are unchanged, as the task's note says.

## Files changed

- `config/omp/context-files/APPEND_SYSTEM.md`:
  - the ROLE CHAIN block at the top;
  - the PROCESS DEFECT line;
  - two contradictions fixed;
  - the role re-stated after its copy of the brief.
- `config/omp/context-files/RULES.md`: two contradictions fixed.
- `config/agents/compaction-brief.md`: the role re-stated.
- `config/claude/CLAUDE.md`: the mirroring duty, and the role in its copy of the brief.
- `scripts/check-coordinator-role.py`: new.

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | The role chain is in the first ~20 lines of `APPEND_SYSTEM.md`, as a block | PASS. Lines 1–11: `## ROLE CHAIN (read first; binding)`, then the task's block verbatim (coordinator → decide / spec / dispatch / verify; "claude + its subagents are the ones who read, research, and write code"; subagents return a compressed result). |
| 2 | The PROCESS DEFECT line | PASS. Line 13: "**Editing a repo file from your own session is a PROCESS DEFECT** (code, config, tests, scripts, instructions under change), even when it is one line and you are sure. The owner has had to say this twice. The only files you write are specs, verdict notes and board state. Caught mid-edit: stop, revert, and dispatch it instead." |
| 3 | The role is re-stated in the compaction brief | PASS. A paragraph after the five items: "Then restate the role chain…: the omp coordinator decides, writes the spec, dispatches and verifies, and never edits a repo file itself (that is a process defect); claude and its subagents read, research and write code. Name which role this session holds." |
| 4 | A check that fails if the block is removed, in the same shape and place as the brief checker | PASS. `scripts/check-coordinator-role.py`, a standalone script beside `check-compaction-brief.py`. It checks all of this list (15 checks). `--selftest` proves it fails on three mutations (output below). |
| 5 | `CLAUDE.md` carries the mirroring duty | PASS. Right under the "dev workhorse" line: "**Your duty is the doing:** you do the reading, the research and the coding the coordinator hands you… never hand implementation back to it. Delegate within yourself, to your own subagents, for atomic context." |
| 6 | Nothing contradicts | PASS, after four fixes (next section). The check greps both omp context files for those phrasings and their general shapes. |
| 7 | Whether a pre-tool hook could enforce it | **It exists; I did not build it.** See the section below. |

**Why the brief is worded for both roles:** the brief also feeds Claude's compactions, through the PreCompact hook. So the restatement says which role does what, and asks the summary to name the role this session holds. It doesn't tell every reader "you are the coordinator".

**Spawned subagents keep their exemption.** The block opens with "A spawned task subagent skips this block: you are the worker". The existing "Your role" clause (do NOT delegate further) is untouched, and the check verifies both.

## Contradictions found and fixed

1. `APPEND_SYSTEM.md`, Anti-dithering: "If you catch yourself implementing directly **for several consecutive turns**, stop". That allowed a few turns of implementing. It now reads "If you catch yourself implementing **at all**, stop: that is a process defect".
2. `APPEND_SYSTEM.md`, Delegation economics: "The workhorse gets the implementation **share**" now reads "gets **all of** the implementation".
3. `RULES.md`: "Never spend more than 3 consecutive turns on pure research" presumed the coordinator researches. It now says: "The coordinator researches nothing in bulk: codebase reading and research go to claude or a subagent. Whoever does research never spends more than 3 consecutive turns on it…"
4. `RULES.md`: "Delegate implementation packages to @task subagents" never named claude. It now reads "to claude in this project, or to @task subagents".

Read and kept, because they're about checking or orientation, not implementing:
- "for orientation you may read 1-2 key files yourself";
- "Run single quick checks yourself";
- "run the concrete check yourself".

## Acceptance 7: the pre-tool hook exists

Source: the installed omp 17.3.4 (`@oh-my-pi/pi-coding-agent`):
- **The hook:** `src/extensibility/extensions/types.ts:1244` declares `on("tool_call", …)`.
- **It can block:** `src/extensibility/shared-events.ts:310` defines `ToolCallEventResult { block?: boolean; reason?: string; input?: … }`. `block: true` stops the tool, and `reason` goes back to the model as the error.
- **Timing:** it fires at arg-prep time, before `tool_execution_start` and before the approval gate.
- **Already in use here:** `omp-privacy-guard.ts:20` and `omp-herdr-guard.ts:16` both block through it.
- **A related mechanism already exists:** `omp-delegation-guard.ts` counts the main session's direct `write`/`edit` calls on `tool_execution_start` and **nudges** after 3 (`DIRECT_THRESHOLD`). It never blocks.

So a blocking "the coordinator may not write code" guard is buildable. **I did not build it** (the task says to establish and report, and the note says instructions and checks only). Two design problems need the owner's call first:
- **Telling a worker from the coordinator at call time.** The delegation guard spots a task worker by seeing a `yield`, which a worker emits at the end, so it is unknown when the worker's first `edit` arrives. A blocking guard needs a reliable signal, for example an env var the task tool sets for its subprocess (unverified), or else it would block the workers too.
- **An allowlist.** The coordinator legitimately writes specs and board state (`docs/task-*.md`, `docs/issue-*.md`, `spikes/`). The guard has to allow those paths and block the rest, which makes it a policy table someone has to own.

**A cheaper intermediate:** `DIRECT_THRESHOLD = 3` in the delegation guard now contradicts "even when it is one line". Lowering it to 1, and counting only non-spec paths, would turn the nudge into an immediate warning without blocking. That is a code change to an extension, so it is outside this task; it's here for the decision.

## Runs

`python3 scripts/check-coordinator-role.py`: 15 PASS, OK (exit 0).

`python3 scripts/check-coordinator-role.py --selftest` (on a temp copy):
```
selftest role block deleted: check FAILED as it must
selftest defect line dropped: check FAILED as it must
selftest contradiction back: check FAILED as it must
selftest OK
```

`python3 scripts/check-compaction-brief.py`: still OK. Adding the role paragraph kept the five items verbatim, and the PreCompact hook now prints the brief including the role. Every live link shows "loaded", including the compaction extension, which has been linked since the last task.

## Not done

- **No blocking pre-tool guard,** for the reasons above.
- **Neither check is wired into a git hook.** "Where that one is" is a standalone script in `scripts/`, and the brief checker isn't in a hook either. Putting the role check in pre-commit (it is pure Python and fast) would make "a future edit cannot quietly delete it" hold at commit time. That's a one-line change in `.githooks/pre-commit`, for the owner to decide.
- **New sessions needed:** running omp sessions keep their old system prompt until restart.
