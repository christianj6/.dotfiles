# TASK: add "never silently resolve a conflict" to the shared rules

Owner's coordinator asked for this to be promoted out of one spec, and gave it its
justification. Small change, real value.

## The rule

Add beside the PROCESS DEFECT line in `config/omp/context-files/APPEND_SYSTEM.md`, and the
same in `config/claude/CLAUDE.md` so both agents carry it:

> **Never silently resolve a conflict — report it.** Two writers on one tree is how a
> verification probe overwrote the owner's real `data/settings.json`; a quiet "fix" during
> a conflict is how it would happen again while looking like housekeeping. If you find
> concurrent changes, a merge you did not expect, or state that does not match what you
> left, stop and say so. Resolving it silently destroys the evidence of which writer was
> wrong.

## Why it belongs in the shared set, not one spec

The three defects of 2026-11-09 share one shape — **a mutation attributed to, or performed
on, the wrong party**:

1. the task dock's `by` defaulting to "the owner" (invented actor);
2. a review recorded in a colleague's name (invented actor);
3. a test server on 8917 writing the owner's real `data/` (a mutation on live state).

Each was found *after* the fact because the action looked legitimate at the time. A silent
conflict resolution is the fourth instance waiting to happen: it is a mutation on live state
that looks like housekeeping.

## Acceptance

1. The rule appears in **both** instruction files, phrased as above, near the process-defect
   line rather than buried.
2. Wording does not imply "never fix" — it says report first, so a genuine trivial fix still
   gets made with the reporter's knowledge.
3. `python3 ~/.dotfiles/scripts/check-coordinator-role.py` still passes (the role block is
   untouched).
4. Nothing else in either file is weakened.

## Note

Keep it short. The value is that it is *there* and specific, not that it is long — every
rule that grew into a paragraph today lost to the shortcut beside it.
