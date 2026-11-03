# `omp-peer` delivery contract (v1)

Owned by **dotfiles** (`config/herdr/skills/herdr-workstreams/peer.py`, installed as `~/.local/bin/omp-peer`). Both prescient's task hub and bro's client call it; this file is the contract they code against. If the behaviour changes, bump the version here and tell both coordinators.

`omp-peer send <target> "<text>" [--wait-reply] [--confirm-timeout S] [--reply-timeout S] [--no-guard]`

## Exit codes

| Code | Meaning | Sender should |
|---|---|---|
| **0** | **Delivered** — the text was seen as a `user` entry in the peer's transcript (with `--wait-reply`, a reply was also printed to stdout) | treat as delivered |
| **1** | herdr/target error — the agent isn't addressable, or `pane send-text` failed | treat as **failed**; do not retry blindly |
| **2** | Fired but **not confirmed** within `--confirm-timeout` | treat as **pending**, not failed — it very often landed |
| **3** | Delivered, but no reply within `--reply-timeout` (usually the peer is on an approval dialog) | the message IS delivered; escalate if a reply was required |
| **4** | The peer's REPL could not be brought into view (nvim-nested) and **nothing was typed** | treat as **failed and safe to retry** |

stdout on success: `delivered <session-file>`. All progress and diagnostics go to **stderr**.

## What "delivered" actually means, and its limits

- Confirmation is **transcript-based**: `omp-peer` fires `herdr agent prompt`, then polls the peer's newest session file until the sent text appears as a `user` entry (needle = first ~24 chars, whitespace-normalised).
- **It only reads omp session files** (`~/.omp/agent/sessions/<cwd-key>/`). Targeting a **claude** pane therefore exits **2 even when the message landed** — claude transcripts live elsewhere. Callers must not treat 2 as "not delivered" for claude targets, and must not resend (that duplicates the work). For claude targets, prefer `herdr agent prompt` + `herdr agent read` for confirmation.
- Session-file lookup is keyed by **cwd**, and covers `$HOME`-relative paths; a peer whose cwd is outside `$HOME` (e.g. `/tmp/...`) can exit 2 after delivering, because omp files that session under a key `candidate_keys()` doesn't produce.
- Nested peers (omp inside nvim) are handled: `herdr agent prompt` refuses with `agent_not_ready`, and `omp-peer` falls back to raw pane delivery **only after** the REPL visibility guard passes (ctrl+a toggle, bounded at two attempts). If the REPL never becomes visible it exits 4 **without typing anything**.
- A paste block can drop the first Enter; `omp-peer` retries the Enter once before judging (only on the raw path).

## Rules for callers (the hub and bro)

1. **One attempt, no client-side retry loop.** Retry semantics belong to the caller's own state machine (`undelivered` in the hub; bro's pending queue). Callers map codes to states.
2. **2 is ambiguous, not failure.** For omp targets: likely delivered. For claude targets: always ambiguous. Never resend on 2 without checking the target's pane.
3. **4 is the only "safe to retry" failure** (nothing was typed).
4. **3 means it landed.** Do not resend; escalate the missing reply if one was required.
5. **Keep the text short.** Pane delivery truncates long messages; anything over ~2 sentences belongs in a file with the path sent as the message (see `rule://agent-pane-messaging`).
6. **Resolve the target at send time.** Agent names encode version + pane (`omp-v31-wdp7`) and change on roll; resolve from `herdr agent list` by cwd/role immediately before sending.

## Suggested mapping (for the hub's `nudged` field)

| omp-peer exit | `nudged` |
|---|---|
| 0 | `ok` |
| 2 | `pending` |
| 3 | `ok` (delivered; no reply) |
| 1 | `failed` |
| 4 | `failed` (safe to retry) |

For a **claude** target, `ok` cannot be proven from exit 0/2 — confirm with `herdr agent read` before reporting `ok`, else report `pending`.

## Decision: the hub does NOT shell out to `omp-peer` (2026-11-03)

Prescient's `agent._deliver` is the nudge path, not this CLI. Rationale (prescient's, accepted):

- `_deliver` already handles the nvim-nested omp case — the same case this contract's exit 2/4 carve out — and is the path hardened by `842f2b7`/`e9e60c0` after the owner twice had to press Enter by hand.
- It yields a richer verdict than an exit code: it can distinguish **"typed but not submitted"** (failed, *not* retryable — retrying duplicates) from "raised with nothing typed" (failed, retryable). `omp-peer`'s exit 1 cannot express that difference.

The **vocabulary stays shared**, which is what matters for callers: both paths report `nudged: ok | pending | failed` plus `retryable: bool` on the item.

| `_deliver` outcome | `nudged` | `retryable` |
|---|---|---|
| nested path, read-back confirms submitted | `ok` | — |
| fast path, prompt returned (typed, nothing read back) | `pending` | — |
| raised, nothing typed | `failed` | **yes** |
| raised, "typed but not submitted" | `failed` | **no** (retry duplicates) |

For **claude** targets `_deliver`'s existing read-back decides: `ok` only when it passes, otherwise `pending`.

This document remains the contract for `omp-peer` itself (bro's client and any other caller), and the source of truth for *why* exit 2 must never be treated as failure.

## Correction (2026-11-03, from prescient's wave-1 report)

**A claude target is ALWAYS `pending`, never `ok`.** This document said "confirm with `herdr agent read` before reporting ok" — but `agent._deliver` only reads the pane back on the **nested-omp** path; a claude target always takes the fast `agent prompt` path, where nothing is read back. So under this contract's own rule a claude delivery can never be *proven*, and the hub reports `pending` for every claude nudge. That is correct behaviour (a pending nudge is not evidence either way; the reaper judges on "still queued AND target idle"), not a bug.
