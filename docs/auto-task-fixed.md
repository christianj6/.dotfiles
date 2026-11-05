# auto-task was dead workspace-wide — fixed

The owner: *"Things should be tracked no matter where I put them in, whether I
give something in through Bro or directly in the chat or whatever."* They were
not, and had not been all day.

## Root cause

```python
def is_coordinator(tasks) -> bool:          # the whole hub list
    for t in tasks:
        if str(t.get("target") or "") == "coordinator":
            return True
```

It scanned **every** item and returned True if *any* was coordinator-targeted.
69 of 100 items are, so **every agent** — including every Claude — was classed a
coordinator, and `autotask_check` returned *"this agent coordinates; its work is
other agents' tasks, not its own card"* for all of them.

Consequence: **auto-task never fired for anyone.** Nothing the owner said was
tracked, from bro, from a chat, from anywhere. That is the real bug behind
"things aren't tracked", and it was invisible because the guard was written to
stop a self-referential loop and had no test for the workhorse case.

## Fix

Per agent, by role:

```python
return (agent.get("agent") or agent.get("kind")) == "omp"
```

The omp is its project's coordinator; its Claude is the workhorse. **Item history
is deliberately not evidence** — a Claude shares its project with its omp, so "a
coordinator item exists in my project" is true of both, which was the bug's shape.

## Verified

- `is_coordinator`: omps True, all six Claude panes False.
- Live `--explain` on bro's Claude: *"work session: 6 tool calls, 45s, no task
  covering it"* — the gate is open where it used to say "this agent coordinates".
- **The harness opened cards.** After the daemon restart: `tk-fd5abeca35f2` (bro)
  and `tk-8b6d25d22b81` (heinzel), both `origin=harness`, both nudged `ok`.
- `open_task` driven directly for heinzel's Claude returned a real id
  (`tk-5a4c87989895`), proving the create path works for a workhorse.

## What I could NOT claim

Heinzel's Claude was mid-turn and **still working** the whole time, so its own
card didn't appear while I watched: `auto_task` only creates for a turn that
either just ended or is running past the cheap-check threshold, and that session's
marker was already consumed before my restart. The create path is proven by direct
drive and by two cards opened for other agents; the *live* appearance of a card
for a still-working Claude was not observed.

That is the same distinction as earlier today: tested vs observed. Stated rather
than rounded up.

## Why it matters beyond the icon

This was never only about colour. A green icon needs a tracked item, and nothing
was being tracked — so the whole "amber → green" pipeline was decorative for
work that came in any way other than a hub task. With this fixed, work arrives in
the hub wherever it came from, and the icon has something real to report.
