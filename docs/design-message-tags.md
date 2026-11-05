# Design: tag the message, not the prose

The owner's insight, and it is the right one: *"workers communicate with each other through tooling that we should be able to either control or wire into. I suspect there's a way that we can just put tags in it."*

**Yes.** Every agent-to-agent message in this workspace passes through one of a handful of senders we own. The sender is known at that moment, so it can be written into the text. No inference, no classifier, no guessing at prose.

## Why shape-classification keeps failing

I have now watched it fail three times:

| Case | What happened |
|---|---|
| coordinator → Claude dispatch | recorded `origin: owner` (`tk-35a1ddfb2295`, `tk-01591d8d2d41`) |
| coordinator pasting a report | indistinguishable from the owner's words |
| worker prose "Both landed, 87 tests OK" | no marker to find |

And the constraint that makes it unfixable by cleverness: a message in a pane is `{"content": …, "role": "user"}`. Every sender produces the same entry. **The answer is not in the text, so it must be put there.**

## The wire

Four senders, all ours:

| Path | Who uses it |
|---|---|
| `omp-peer send` (`~/.local/bin/omp-peer`, `config/herdr/skills/herdr-workstreams/peer.py`) | omp ↔ omp, coordinator → worker |
| `prescient` `agent._deliver` (`prescient/gantt/agent.py`) | hub nudges, dock replies |
| `herdr agent prompt` (direct) | agents that skip the wrapper |
| `agent-discord` relay (`config/herdr/plugins/agent-discord/bot.py`) | external messages in |

All of them type plain text today. `omp-peer` sends `text` verbatim — checked.

## The tag

One line at the top of every relayed message, and nothing else changes:

```
[from:coordinator project:bro id:omp-v35-wdp5]
```

- `from:` is the role of the sender — `owner | coordinator | worker | harness | bro`
- `project:` its project, so cross-project relays are attributable
- `id:` the sender's agent name, for debugging
- Agents sending to each other can also use `agent:` for a free-form agent identity

The receiving harness reads the tag and is done. **One regex, at the top of the prompt, on data that now carries the answer.**

## How each sender applies it

1. **`omp-peer send`** — prepend `[from:coordinator project:<cwd project> id:<self>]` automatically when the caller does not supply one. It already knows its own pane and the target's project. A `--from` override for special cases (the owner relaying by hand).
2. **prescient `_deliver`** — it already receives `by` (that is its whole contract). Prefix `[from:<by> project:<project> id:<caller>]`. This is the same fact the deliveries table would hold, written where it is cheap: in the text.
3. **`herdr agent prompt` direct** — agents must not use it bare. `AGENTS.md` gains: *"never type into another agent's pane by hand; `omp-peer send` puts the tag on for you."* Cheap to enforce by convention, and the tag degrades gracefully if missed (see below).
4. **`agent-discord`** — prefixes `[from:owner source:discord]`, because a message from Discord **is** the owner speaking.

## Why a tag beats a deliveries table

I previously specced a `deliveries` table plus a lookup. The tag is better on three counts:

- **It travels with the text.** The answer is present at the point of use; no window, no digest match, no race between "when was it delivered" and "when did the turn start".
- **It survives copies.** A message pasted, forwarded, or quoted keeps its origin.
- **It is debuggable by a human.** You can read a pane and see who sent what, without a database.

Keep the table as a *secondary* record if prescient wants one for audit. It is no longer the mechanism.

## Parsing, and the fallback that must stay

```python
TAG = re.compile(r"^\s*\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]")
```

- **Tagged** → that role, exactly.
- **Untagged** → the current behaviour (machinery shapes first, then shape classification, defaulting to `owner`). Untagged is overwhelmingly the owner typing, which is why `owner` stays the safe default rather than `harness`.
- **`[from:owner]` must win over every shape heuristic** — the owner's own words can look like anything.

This is strictly additive: every message works exactly as today until the senders start tagging, and each sender can adopt independently.

## Acceptance

1. `omp-peer send` prefixes a tag automatically; `--from` overrides it.
2. prescient `_deliver` prefixes `[from:<by> …]`; the hub's own nudges arrive tagged `harness` or `owner` as appropriate.
3. The plugin parses the tag and returns its role, **before** any shape rule.
4. `[from:owner]` beats every heuristic — a tagged owner message that looks like a round spec is still `owner`.
5. Untagged still falls back to today's behaviour, unchanged, with a test for each class.
6. An agent-to-agent relay is recorded `origin: agent`, never `owner` — the `tk-35a1ddfb2295` / `tk-01591d8d2d41` case, replayed and shown fixed.
7. The lifecycle still completes for a tagged owner request typed through bro's omp.

## What this does not solve

An agent that pastes text **into its own** turn, or that types into a pane bare, produces an untagged message. The tag is a strong default, not a guarantee — which is why the fallback must stay and why "don't type bare" belongs in the agent rules. The difference from today is that the common paths now carry the answer, and the remaining gap is a rule violation rather than an unavoidable property of the system.
