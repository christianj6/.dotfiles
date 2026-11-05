# TASK: a full task lifecycle must work with nothing pre-created in prescient

Repo: ~/.dotfiles. File: `config/herdr/plugins/lifeview-fallback/lifeview.py` + `test_lifeview.py`.
Owner's requirement, verbatim: *"I want a full task lifecycle even if something isn't created through Prescient. That shouldn't be a requirement, and our harness should be able to somehow handle that. Distinguishing between a task that I'm giving it and you know, just communication from other coordinators."*

## The failure, reproduced

I asked bro through its own pane: *"Can you check the current git branch in the bro repo and tell me what it is? Just run the command."*

- bro answered correctly.
- **No hub item was created.** Item count stayed at 160.
- The icon went working then straight back to **idle** — so the owner never saw green.

Diagnosed by calling the real function:

```
prompt    : "Can you check the current git branch in the bro repo..."
calls     : 1      span: 6.3s
provenance: owner
autotask -> None | "not working, and no turn ended in the last 2 min"
```

The gate that blocked it is the **trivial threshold**:

```python
if not (calls >= WORK_MIN_TOOL_CALLS or (calls >= 1 and span > WORK_MIN_SPAN_S)):
    return None, "trivial so far: ..."
```

`WORK_MIN_TOOL_CALLS` is 2. A plain owner request that takes **one** tool call is
judged incidental and never becomes a task — so the lifecycle (task → amber →
ready → green) cannot complete for anything short of a multi-step job.

## What to change

**1. The threshold must not gate the owner's own requests.** It exists to filter
*incidental activity* (a lookup while chatting), not to decide whether the owner
asked for something. An attributed `owner` or `agent` turn that used **at least
one** tool call did work:

```python
trivial = not (calls >= WORK_MIN_TOOL_CALLS or (calls >= 1 and span > WORK_MIN_SPAN_S))
if trivial and not (origin in ("owner", "agent") and calls >= 1):
    return None, "..."   # machinery is already refused earlier; this is the truly-idle case
```

Keep the threshold for anything else. Do **not** lower `WORK_MIN_TOOL_CALLS`
globally — that would start carding conversational lookups.

**2. Confirm the rest of the chain fires for an auto-created task.** The card is
created `queued` with `target: coordinator`. For the ring to go green the item
must reach `ready` — either the agent marking it (it is nudged, so it usually
does) or auto-ready. That path is already implemented; it needs one test showing
`queued → working → ready` for a card the harness created, not one the owner made.

**3. Keep the provenance distinction the owner asked for, in the same test.** A
coordinator's message to a worker must NOT produce an owner card: provenance
`agent` for `Round N:` / `Spec:` / a spec path, `machinery` (no card) for
`<task-notification>` / continuation summaries.

## Acceptance — show, do not describe

1. **The lifecycle, auto-created only.** With the hub holding NO open item and no
   task created by prescient: a one-tool-call owner request through the agent's
   pane produces a hub card, and that card reaches `ready`, and `project_icon`
   for that project returns `ready`. Assert the sequence, not just the end state.
2. The card's `origin` is `owner`, and its text is the owner's request.
3. A `Round N: …` prompt produces a card with `origin: agent`.
4. A `<task-notification>` prompt produces **no** card.
5. A zero-tool-call conversational turn still produces no card.
6. Existing tests pass; do not weaken an assertion to make one pass.

## Rules
- Run `python3 config/herdr/plugins/lifeview-fallback/test_lifeview.py`. No project-wide suites, no formatters.
- Commit locally citing this task and the owner's requirement. **Do not push.**
- Report: what changed, the lifecycle sequence you observed, both provenance cases, and anything you chose not to do.
