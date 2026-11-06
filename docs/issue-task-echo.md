# Bug: every message into a pane becomes a hub task (owner: "a kind of echo")

Owner's report, 8 items cleared by prescient's coordinator today. Symptoms: each
arriving message becomes `auto: <the message>`, `project=prescient`,
`target=coordinator`, `origin=owner`, one per dispatch/report/reply.

**Two causes, both mine, both reproduced.**

## Cause 1 — the daemon runs code from before the tag parser

The tag work landed at **19:51** (`30dbf2b`). The lifeview daemon started at
**18:44:36** and is still that process. So every message is being classified by the
*old* shape rules, with no tag to read.

Proven by the item timestamps: `tk-e36f300b9980` at **19:52:43** carries a tag in
its text (`auto: [from:worker project:bro id:claude…]`) — the tag was on the wire and
the daemon ignored it, because the running process predates the parser.

**Fix: restart the daemon.** That alone fixes tags and the pre-fix runs.

## Cause 2 — the coverage check is still agent-keyed (the real echo)

Even on current code, a worker with an open hub item keeps opening new cards. The
gate is:

```python
covering = [t for t in tasks_of(agent, tasks) if t.get("state") in COVERING]
```

`tasks_of` matches on `t["agent"]` or a `dest` of `agent:<name>` — and hub items have
**`agent: null`** with a *role* dest. So it is **always empty**:

```
tasks_of(claude-v2-wdpc, [one open coordinator item]) -> []      # cannot ever cover
project_items('prescient', [same item])              -> 1        # this is the item
autotask -> 'auto: Both landed, 998 tests OK' | "no task covering it"
```

This is **the same class as the auto-ready bug I fixed earlier** (agent-keyed
matching against `agent: null`). I fixed it in `ready_check` and left auto-task's
`covering` untouched, so the two halves now disagree about what "covered" means. That
asymmetry is why the echo survived my earlier fix.

**Fix:** the coverage check must be project+role keyed, exactly like
`ready_candidates` — an open item for this project and role covers this agent's work:

```python
covering = [t for t in project_items(agent.get("project"), tasks)
            if t.get("state") in COVERING and t.get("target") == ("coordinator" if is_coordinator(agent, tasks) else "dev")]
```

or, more simply, "any open item in this project covers this agent" if the project has
one work stream. Decide and state the choice.

## Cause 3 (owner's ask, #1 by priority) — a pane message should not card itself

The owner's priority: *"why does a pane message become a hub item at all — even
correctly tagged, a card per dispatch is noise, and a coordinator's dispatch to its
own worker arguably should create none."*

Agreed, and it is the deepest fix: **a coordinator dispatching to its own worker
should create no card.** The dispatch is already a work instruction; carding it makes
a card per instruction, and the worker then reports, and *that* gets carded too — the
echo is structural, not a coincidence.

Proposal: auto-task never cards a turn whose prompt is **an agent-to-agent message**
(`[from:coordinator]` / `[from:worker]`), regardless of project. Those are comms. Only
`owner`, untagged-human, and `agent`-by-shape (a round spec handed *to* the worker by a
human) should card. Where a coordinator's own work genuinely needs tracking, it
creates the card itself — that is what the hub is for.

## Cause 4 — the last two were the OWNER's messages

Possibly a separate class (cross-check `cutover-result.md §3`, the self-referential
loop). With the tag now on the wire and `[from:owner]` beating every shape rule, an
owner message should classify `owner` and the coordinator gate will let it through —
which is *correct* (that is the lifecycle working). The question is whether the owner
wants his own pane replies carded. If not, say so; the owner-origin exemption in the
coordinator gate should be narrowed to "owner asked for work", not "owner said
anything".

## Also reported — `omp-peer` does not resolve agent names

`omp-v25-wdp9` failed once dotfiles rolled to `omp-v35-wdp9`. Same class as
`83173fa`: a stored name goes stale when panes roll. `omp-peer send <name>` should
resolve the *current* agent for that pane/project, or accept a pane id. Worth fixing
in the same pass — it is why one message went out untagged (the sender lookup failed
and the tag was skipped).

## Acceptance

1. Daemon restarted; a tagged `[from:worker …]` message creates no card.
2. A worker with an open project item creates no new card for its next turn
   (coverage is project+role keyed). Show `tasks_of` replaced and the echo impossible.
3. A coordinator's dispatch to its own worker creates **no** card (owner's ask #1).
4. An owner request in a pane still creates one card and completes the lifecycle.
5. Untagged messages behave as today.
6. `omp-peer send` resolves a stale agent name to the live one, or refuses with a
   message naming the live agent.
