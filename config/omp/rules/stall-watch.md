# Stall-watch: never let the workhorse sit idle unnoticed

The failure this guardrails against (owner-reported 2026-11-02): the claude workhorse reached a stopping point and **nothing noticed for 8 minutes**. The coordinator had armed a watcher on a *commit-message pattern* instead of on the *pane state*, and was busy elsewhere when the commit landed under a different message. A dev "short circuit" — work stops, nobody picks up the next item.

## Rule for the coordinator

**Every delegated task gets a live watcher on the PANE, not on a guessed output pattern.** After dispatching a spec:

1. Arm a watcher that fires on the pane's **settled state** — `herdr agent wait <target> --until idle|done --timeout <ms>`, or `herdr pane wait-output` on a marker the spec REQUIRES the workhorse to print. Never arm only on `git log | grep <message>`: commit subjects vary and a watcher on the wrong pattern is silently blind.
2. Keep **at most one delegation in flight per workhorse**. The next item waits until the current one reports — a second prompt queues into a busy REPL and its task can be silently interleaved or lost.
3. On settle: read the pane (or the report file) **immediately**, then either dispatch the next approved card or stop with a reason.
4. If the watcher times out: check `herdr agent list` for `blocked` (approval dialog) before assuming anything else.

## Report contract (both directions)

The workhorse ends every task by printing a final line containing `DONE:` plus one sentence, **and** writing the report to a file. The coordinator treats a report + `DONE:` line as the handoff signal — neither alone is sufficient (pane text is not a record; a file with no signal is invisible until polled).

## Standing check between turns

Whenever the coordinator takes any action (including answering the owner), it first asks: *is a workhorse idle, and does it have unreported output?* One `herdr agent list` is cheap; an idle workhorse with a finished task is the expensive failure.

## Why not a background daemon

A watcher daemon that auto-dispatches the backlog is tempting and wrong: it removes the judgment step (owner approval, ambiguity checks, logical stopping points) that the coordinator exists to provide. The guarantee is *noticing*, not auto-grinding: notice → read → decide.
