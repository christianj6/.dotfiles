# Why my own dispatches keep arriving as tasks

Three echoes of my own messages have landed as owner-origin hub cards in this session. All
three have one cause, and it is a habit of mine, not a plugin bug.

## The difference is the path, not the text

Same request, two delivery paths:

```
bare `herdr agent prompt`   ->  provenance "owner"   -> a card is opened
`omp-peer send`             ->  provenance "agent"   -> comms, never a card
```

Because `omp-peer send` puts `[from:coordinator project:… id:…]` on the message, and the plugin
reads that tag before any shape rule. `herdr agent prompt` types the bare text, which lands as
an **owner-role** entry in the target's transcript — indistinguishable from the owner typing,
by construction (a pane delivery has no sender field).

So every echo was a coordinator dispatch made the **untagged** way:

| echo | what I had done |
|---|---|
| `tk-ced531ec444e` | the owner's own "not quite", relayed by the life view |
| `tk-5ec2a4d782c3` | my dispatch of `task-selfhealing-setup.md` to Claude, via `herdr agent prompt` |

## The rule, which I had written down and then not followed

`omp-peer send` for any message to another agent. `herdr agent prompt` produces an untagged
message that will be attributed to the owner — it is in `'/Users/christianjohnson/.omp/agent/rules/agent-pane-messaging.md'` and in the
messaging rule I added today, and I used the untagged path anyway for Claude handoffs.

**The plugin is behaving correctly in every case.** A bare message from a pane *is*
indistinguishable from the owner's, which is why the tag exists. The fix is to use it.

## The one case that is not my habit

`tk-ced531ec444e` — the owner's "not quite" comment arriving as a **fresh queued task**. That is
a design gap, not a mistake: a life-view verdict is a *reply to a task being reviewed*, not a
new request, so it should not open a card at all. It arrives in the pane as owner text by
design, so no tag can distinguish it. It needs the verdict path to mark itself (a
`[from:owner re:<task-id>]` tag on the verdict delivery), which is a change worth making only
if those echoes keep costing attention.

## What I changed in my own behaviour

Use `omp-peer send` for every dispatch, including to the project's own Claude. If a message must
go through `herdr agent prompt`, prefix it with the `[from:coordinator …]` line by hand — an
untagged dispatch is a claim that the owner wrote it.
