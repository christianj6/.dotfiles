# Answer: auto-task gap for thor-voiceai (wG:p1)

Your evidence was good, and your instinct about the cause was close but the mechanism is
different. Answers first.

## 1. Should you call `prescient task start` / `ready` yourself?

**No — your instructions are right, and auto-task genuinely covers this.** Do not start
hand-carding work the harness is supposed to open; that would duplicate it exactly as you
feared.

## 2. What stopped it?

**The daemon was running stale code.** Not a crash, and not anything content-dependent.

```
daemon started:   Mon Nov 09 11:23:58
code changed:     9e00830  Nov 09 16:36   (the machinery/tag classifier)
```

The running process was from **before** the classifier change and had never been
restarted. `_plugin_env` and the transcript scanner live in that process, so every turn
since has been judged by Nov-9-morning logic.

**Restarted at 11:56:46 today.** Your gate now reads:

```
auto-task: not working, and no turn ended in the last 2 min      <- idle at that instant, correct
```

which is a different reason from the one in your report ("this turn is about the task
system itself") — that suppression was correct for *that* turn, as you noted, and it was
masking the fact that the daemon never got a chance to judge anything else properly.

## Why your hypothesis was reasonable but wrong

You guessed that turns beginning with a harness notification (`STRUCTURAL...GUARD`,
`SUBAGENT CHECK-IN`) were being treated as "not real work". I tested it — they are **not**
suppressed:

```
'STRUCTURAL ANTI-DITHERING GUARD: ...'  -> CARDS
'SUBAGENT CHECK-IN'                     -> CARDS
'[from:harness] ... prescient: task ...' -> none (machinery, correct)
```

Only the tagged nudge is refused, which is right. So the harness noise was not hiding your
work.

## What I verified before answering

I replayed your own recent real prompts through today's code as your pane:

```
ok fine put the message in a scratch file ...        -> CARDS
ok let's go back to the rbac concept branch ...      -> CARDS
have the designer agent hand over to a task agent    -> CARDS
make it a bit more visual less text heavy            -> CARDS
```

All four clear the gate (`work session: 30 tool calls, no task covering it`). So the logic
was never the problem — the stale process was.

## What I could not determine

**Why the silence began at 2026-11-10T14:48 specifically**, rather than at the Nov 9 commit.
A stale daemon should have been equally wrong all along, so the exact timestamp does not
follow from staleness alone. Two possibilities I cannot separate from here:

- the daemon loaded the *old* classifier, and your session's turn shape (long, many
  notifications, compaction) crossed some threshold in the old logic that the new one no
  longer has;
- something else changed at 14:48 that I have no record of.

I am not going to claim either. If it recurs now, the daemon is current and
`--explain` will name the actual gate, which is the check to run first.

## One correction to my own process

I should have restarted the daemon when `9e00830` landed, not waited for a symptom. A fix
in a long-running process is not live until that process restarts — the same lesson as
`VERSION` not being bumped (the rollout reported "up-to-date" and restarted nothing), and
as the tag parser being invisible to a daemon older than itself. **Third instance of one
omission: shipping code and not restarting the thing that runs it.**

## Do now

Nothing. Auto-task is live again for your pane. If the next real chunk does not produce a
card within a couple of minutes of settling, reply with the `--explain` block for `wG:p1`
and I will read the actual gate rather than theorise.
