---
name: coordinator-network
description: Who may talk to whom across projects — omp coordinators talk to each other, omp and claude talk only within one project, and claude panes never talk across projects. Read when messaging another project's agent, handing off cross-project work, or when two claude panes need to exchange something.
---

# Coordinator network

Every project has one omp coordinator and one claude workhorse. The topology follows from that split: coordination crosses project lines, implementation does not.

| Link | Scope | Status |
| --- | --- | --- |
| omp ↔ omp | across projects | Yes: the default and expected path |
| omp ↔ claude | same project tab only | Yes: specs down, reports up |
| omp ↔ claude | across projects | No: go through that project's coordinator |
| claude ↔ claude | across projects | Discouraged: do not do it |

## omp ↔ omp across projects

Coordinators talk to each other using this repo's tools:

- **`omp-peer`** for delivery with transcript confirmation (`omp-peer send <name-or-pane> "<instruction>" [--wait-reply]`). The address book is `herdr agent list`.
- **`hub`** for session-registered peers.

Use it to:

- Ask another project's coordinator for context.
- Hand off cross-project work.
- Broadcast a decision.

The usual pane-messaging limits apply: anything over about two sentences goes in a file, and the message is the path plus one line (`rule://agent-pane-messaging`).

## omp ↔ claude within a project

The coordinator and the claude workhorse in the SAME project tab talk freely: specs go down, reports come up. A coordinator does not message another project's claude, even for a quick question. It asks that project's coordinator, which decides whether its workhorse gets involved.

## claude ↔ claude across projects

Do not do it. claude stays focused on its own project; cross-project coordination is the coordinators' job, never the workhorses'.

If two claude panes need to exchange something, route it through their omp coordinators:

1. The claude that needs something reports it to its own coordinator.
2. That coordinator asks the other project's coordinator.
3. The other coordinator gets the answer, from its own context or its own workhorse, and replies.
4. The first coordinator passes the result down to its claude.

## Why

Workhorses hold deep project context. Pulling a claude out of its project into cross-project chatter destroys focus and duplicates coordinator work.
