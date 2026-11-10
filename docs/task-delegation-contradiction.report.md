# Report: the line that contradicted the sub-agent trigger (docs/task-delegation-contradiction.md)

Committed locally, not pushed. Live at the next omp session start (`APPEND_SYSTEM.md` is symlinked).

## Change

**One line deleted** from `config/omp/context-files/APPEND_SYSTEM.md`, Delegation rules:

```
- File reading: for orientation you may read 1-2 key files yourself; delegate bulk reading to the workhorse or a subagent.
```

Nothing else changed. The trigger block, the brief template, the self-check and the ratio are untouched.

**`config/claude/CLAUDE.md`: no leftover found, nothing changed.**
- Its old soft line ("Stay inline for a handful of tool calls …") was already folded into the trigger's exception by the previous commit.
- Its only other delegation mention is line 6, "Delegate within yourself … (see 'Sub-agents for atomic context')". That is a pointer to the trigger, with no threshold of its own.

## Proof: one reading threshold

```
$ grep -n "1-2 key files" config/omp/context-files/APPEND_SYSTEM.md
(nothing)

$ grep -nE "([0-9]+(-[0-9]+)?|~[0-9]+|a few|handful|one or two|couple)[^.]{0,40}(read|reads|files?|searches|calls|lookups?)\b|\b(read|reads|files?|searches|calls|lookups?)[^.]{0,20}(more than|fewer than|up to|at most) ?~?[0-9]" \
    config/omp/context-files/APPEND_SYSTEM.md config/claude/CLAUDE.md
```

Every hit, in both files:

| Hit | What it is |
|---|---|
| "More than ~3 reads/searches to answer one question → stop and dispatch it" | **The threshold.** |
| "a small lookup whose target you know (1-3 calls) stays inline" | The same threshold, its inline side. |
| "a turn with more than 5 inline reads and no sub-agent says why in its report" | The audit of that rule: per turn rather than per question, and asks for an explanation rather than setting a second limit. The task said leave it alone. |
| Compaction brief: "more than ~3 reads/searches … goes to a sub-agent" | The same threshold, re-stated. |
| "anything over ~2 sentences goes in a file" (omp) | Message length. Not about reading. |
| lifeview auto-task "2+ tool calls, or one running >90 s" (both) | The harness's card rule. Not about reading. |

A second grep for soft reading wording (`orientation|bulk read|handful|you may read|read … yourself`) matches only the trigger's own sentence, "Bulk reading is what burns context".

## Outside both files: noted, not touched

`config/omp/context-files/RULES.md:3` says "Whoever does research never spends more than 3 consecutive turns on it without producing an artifact". That measures research turns without output, not reads per question, so it doesn't compete with the trigger. It is outside the two files this task names.

## Checks

- `check-delegation.py --rules`: OK. Both files still carry the trigger, the brief template, the end-of-turn self-check, the ratio target and the command.
- `check-coordinator-role.py`: OK. `check-compaction-brief.py`: OK.
- **`python3 ~/.dotfiles/scripts/check-delegation.py --omp` runs verbatim**, both from `~/.dotfiles` and from another project's root (prescient).
  - It finds the newest omp session for the current folder and prints counts, ratio and over-threshold turns, then `BELOW TARGET` or `OK`.
  - It exits 0 either way; only `--strict` makes a miss exit 1, so the self-check never fails a turn.
