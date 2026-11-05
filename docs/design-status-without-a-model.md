# Design: agents asking each other "what are you doing" should not cost a model call

The owner: *"It occurs to me that this should provide a way for agents to know what each other is doing without needing to go through language model generations. It also might provide Bro the tooling it needs to be able to provide status updates. Maybe you can kick that wherever it belongs in case that opportunity is right in front of us."*

It is right in front of us. The machinery exists and one caller is not using it.

## What already answers "what is X doing", with no model

`GET /api/tasks/status?project=<p>` — the resolver. Verified live, all six projects, instant:

```
bro            ready    2 tasks are ready for your verdict
dotfiles       ready    2 tasks are ready for your verdict
heinzel        idle     nothing open
thor-voiceai   idle     nothing open
marketing      idle     nothing open
prescient      working  it is busy with something nothing here tracks
```

That is a **structured answer to the question**, already computed from the hub plus
each project's own `prescient-status.json`, with a `why` sentence written to be read
aloud. No generation involved.

And `GET /api/agent-board` is the same for the whole workspace: every agent, its
project, its live state, its open items.

## The gap

**Bro does not call either one for status.** `voicebridge.status_answer()` reads
`status.live(project)` (the hub's open items) and falls back to a stale `STATUS.md`:

```
bro       live = "Right now, from the task list ... - tk-01741874..."
heinzel   live = ''                        <- no items: falls through to the doc or an offer
```

So the answer quality depends on `STATUS.md` being fresh, and the `why` sentence the
resolver already wrote is thrown away. Worse: when there is nothing open, bro offers
to *ask the coordinator* — a round trip through another model — to learn something
already on disk.

## The three things this unlocks

**1. Coordinators can ask each other without a generation.**
A CLI verb, no model in the loop:

```
prescient status --project thor-voiceai     # {status, why, agent, open items}
prescient status --all                      # one line per project
```

An omp asking "what is heinzel on" gets a fact, not a conversation. That is a tool
call, not a turn.

**2. Bro answers from the resolver, and says the resolver's sentence.**
`status_answer(project)` should ask `/api/tasks/status` first and speak its `why`
verbatim — it was written for exactly that ("a task is ready for your verdict").
`STATUS.md` stays as the fallback for a project the hub knows nothing about, not the
primary source. When the resolver says `idle / nothing open`, bro says *that*, instead
of offering to go and ask.

**3. The tag work pays off here too.**
Because messages now carry `[from:coordinator project:bro …]`, a status answer can
name who is asking — an omp asking about a peer's state does not need the same
phrasing as the owner asking. One call, correctly attributed.

## What NOT to do

- **Do not add a tool that lets an agent ask another agent to describe itself.** That
  is the model-in-the-loop round trip this is trying to remove. The state is already
  written down; read it.
- **Do not synthesise prose from the structured answer with a model** when the
  resolver already returns a `why` written for speech.
- **Do not make the CLI the only path.** The HTTP endpoint is the primitive; the CLI
  is a convenience for a pane that wants a one-liner.

## Acceptance

1. `prescient status --project <p>` prints the resolver's `{status, why}` and the open
   item ids, **without** any model call, for a project that is `ready`, one that is
   `working`, and one that is `idle`.
2. `prescient status --all` prints one line per project.
3. Bro's `status_answer(project)` returns the resolver's `why` verbatim when the
   resolver answers, and only falls back to `STATUS.md` when it does not.
4. An `idle / nothing open` project produces "nothing open" — **not** an offer to go
   and ask the coordinator.
5. Existing `status_answer` tests still pass; the doc fallback still works when the
   hub is down.
6. No new model calls anywhere in the status path — assert by driving it with the
   model client stubbed to raise.

## Where this belongs

- `prescient status` CLI + `--all`: **prescient** (it owns the resolver).
- `status_answer` reading the resolver first: **bro** (its own voice path).
- No plugin change: the plugin already consumes `/api/tasks/status` for the icons.

Each is independently shippable, and item 1 is the one that makes "agents know what
each other is doing" true without a generation.
