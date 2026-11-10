# TASK: remove the line that contradicts the sub-agent trigger

The trigger block is good. One line **above it** undermines it, and it is the same
"prose that loses" problem the owner has now raised three times.

## The contradiction

`config/omp/context-files/APPEND_SYSTEM.md`, in **Delegation rules** (line 73):

```
- File reading: for orientation you may read 1-2 key files yourself; delegate bulk
  reading to the workhorse or a subagent.
```

and three lines below it, added today:

```
- **The trigger.** Before any read-heavy or multi-file exploration, count the calls you
  are about to make. **More than ~3 reads/searches to answer one question → stop and
  dispatch it** … If your first instinct is "I'll just read these files", that is the
  trigger.
```

Two rules, different thresholds ("1-2 key files" vs "more than ~3"), and the earlier,
weaker one is read first and reads like permission. An agent skimming the list takes
the permissive line. **That is exactly how the coordinator rule failed too**: present,
contradicted, unenforced.

## What to change

1. **Delete the "1-2 key files" line.** The trigger block already carries the exception
   ("a small lookup whose target you know (1-3 calls) stays inline"), so the old line is
   pure contradiction — and its own wording ("delegate bulk reading", with no threshold)
   is the phrase that made nothing happen.
2. **Check Claude's file for the same leftover.** `config/claude/CLAUDE.md` has its own
   idioms; grep both for any other soft reading/delegation line and remove or fold it
   into the trigger, so there is exactly **one** rule and one threshold.
3. **Do not touch** the trigger block, the brief template, or the ratio measurement —
   they are right.

## Acceptance

1. `grep -n "1-2 key files" config/omp/context-files/APPEND_SYSTEM.md` returns nothing.
2. Exactly **one** reading-delegation threshold exists across both instruction files, and
   it is the ~3-reads trigger. Show the grep that proves no second threshold survives.
3. Both files still contain: the trigger, the brief template, the end-of-turn self-check,
   and the ratio target.
4. `python3 ~/.dotfiles/scripts/check-delegation.py --omp` still runs (it is the
   end-of-turn check the doc points at, so it must work verbatim).
5. No other instruction is weakened — this only removes a contradiction.

## Why this matters more than it looks

The owner's complaint is not that the rule is missing; it is that agents do not follow
it. Every time we have added a rule without removing the permissive line beside it, the
permissive line won. That is the whole lesson of today: **a contradiction is worse than
a gap**, because a gap is followed by nothing while a contradiction licenses the easy
path and looks legitimate.
