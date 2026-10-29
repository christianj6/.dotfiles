---
name: agent-pane-messaging
description: How to instruct another agent through a terminal pane — long herdr pane send-text messages truncate silently and never submit on their own; anything over ~2 sentences goes in a file and the pane message is the path plus one line. Read before using herdr pane send-text, tmux send-keys, or any pane-keyed message delivery.
---

# Messaging an agent through a pane

Two independent failure modes bite here, and they look identical from the outside:

1. **Silent truncation.** `herdr pane send-text` (and `tmux send-keys` with long text) truncates long messages mid-sentence, without error. A worker that receives half an instruction acts on half an instruction.
2. **No submit.** `send-text` does NOT press Enter. Text without a separate `herdr pane send-keys <pane> enter` sits in the pane unread — which looks exactly like truncation, so it gets retried the same broken way.

## The rule

- Anything longer than about two sentences goes in a **file**. The pane message is the **path plus one line of why**.
- Always send the submit key (`enter`/`Return`) as a **separate call** after the text. Better: use `herdr agent prompt <target> <text>` for registered agents — it handles paste + submit as one ordered action.

## Why a file, not a paste

- **The recipient can re-read it.** A truncated message is gone; a file survives a context compaction, which happens on long-running work.
- **It outlives the session.** The brief is on disk for the next agent, and it is a record of what was asked.
- **It can be reviewed.** The sender can diff what was asked against what landed; a pasted message leaves no artifact.

## Verify delivery

After sending, confirm the message actually landed (read the pane tail, or `herdr agent read`) before assuming the worker saw it. Silence or an empty input box means it did not submit — fix the submit, do not resend the text.
