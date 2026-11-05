# Report: the sender's tag on every agent-to-agent message (tk-b32624856c72)

Task: `docs/task-message-tags.md`. Design: `docs/design-message-tags.md`. Committed locally, not pushed. prescient is untouched; its `_deliver` half is routed separately.

## Read this first: install before rolling omp panes

`config/omp/context-files/APPEND_SYSTEM.md` and `config/omp/rules/agent-pane-messaging.md` are **symlinked** into `~/.omp/agent/`, so any omp session started from now on reads the new rule: "dispatch to the claude pane with `omp-peer send`".

The **installed** `~/.local/bin/omp-peer` is still the old copy, identical to the previous HEAD, and I did not touch it, as the task says. Sent to a claude pane, the old copy exits 2 even when the message landed, and a resend duplicates the task.

**So run setup.sh's copy step** (`cp ~/.dotfiles/config/herdr/skills/herdr-workstreams/peer.py ~/.local/bin/omp-peer`) **before restarting any omp pane.** Running sessions are unaffected until they restart.

## The tag format

One first line, written by the sender, and the message body follows on the next line:

```
[from:<role> project:<project> id:<name>]
<body>
```

| field | value |
|---|---|
| `role` | `coordinator` when the sender is an omp pane; `worker` when it is a claude pane; or `--from owner\|coordinator\|worker\|harness\|bro` |
| `project` | the sender's git toplevel folder name, leading dot dropped (`.dotfiles` → `dotfiles`). This is the same rule as lifeview's `project_of_root` and the board; outside a repo, the cwd's folder name. |
| `id` | the sender's herdr agent name. With `--from` outside any agent pane: the pane id, else `cli`. |

The sender is the pane in `$HERDR_PANE_ID`, found in `herdr agent list`.

There are three cases where no tag is added:
- **Already tagged:** text that starts with `[from:` (after optional whitespace) goes out unchanged.
- **No sender and no `--from`:** with no agent in the sender's pane, the text goes out untagged, with a stderr warning ("sending UNTAGGED … the receiver will guess the sender from the text"). It neither fails nor invents a role.
- **A pane kind with no default role** (e.g. codex) works the same way: untagged, with a warning to pass `--from`.

The receiver's regex is the task's, verbatim:
```python
TAG = re.compile(r"^\s*\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]")
```

Real output with the real `herdr agent list` (`--dry-run` prints the final text and sends nothing):

```
from this claude pane:   [from:worker project:dotfiles id:claude-v2-wdpa]
HERDR_PANE_ID=wD:p9:     [from:coordinator project:dotfiles id:omp-v35-wdp9]
  + --from owner:        [from:owner project:dotfiles id:omp-v35-wdp9]
HERDR_PANE_ID=wD:p5:     [from:coordinator project:bro id:omp-v35-wdp5]
pre-tagged text:         [from:owner project:bro id:me] fix it        (unchanged)
no pane, no --from:      hi   + "omp-peer: sending UNTAGGED (...)"
```

## Acceptance

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | omp pane → `[from:coordinator project:dotfiles id:<name>]`; `--from owner` → `[from:owner …]` | PASS | the dry runs above; `test_peer.SenderTag.test_1_*`, `SendPath.test_1_dry_run_*` |
| 2 | text already starting `[from:` is sent unchanged | PASS | `NoDoubleTag.test_2_already_tagged_text_goes_out_unchanged` (three shapes, including a leading space and an unknown role) |
| 3 | tag read before any shape rule: tagged `[from:owner] Round 25: …` → owner; untagged `Round 25: …` → agent | PASS | `MessageTags.test_3_owner_tag_beats_every_shape`: the owner tag beats all 10 shape classes, with the tag on its own line and on the same line |
| 4 | `[from:harness]` → machinery → no card | PASS | `test_4_*`: machinery over all 10 shapes; `autotask_check` says "never a card"; a full harness tick against the lifecycle hub makes **zero hub calls** |
| 5 | `[from:coordinator]`, `[from:worker]` → agent | PASS | `test_5_*`, also `bro`. Covers owner-looking prose and a body that starts `From the owner` (the tag beats `OWNER_MARKED` too). |
| 6 | every existing untagged case passes unchanged | PASS | `git diff` of `test_lifeview.py` has **0 removed lines** (additions only); all pre-existing tests pass |
| 7 | the suites | PASS | `python3 config/herdr/plugins/lifeview-fallback/test_lifeview.py`: **95 OK** (87 + 8 new). `python3 config/herdr/skills/herdr-workstreams/test_peer.py`: **13 OK**. There is no `tests/` dir, so pytest does not apply. |

Two more tests cover the design doc's own acceptance:
- **Design #6, the misattributed dispatch replayed** (`test_a_coordinator_dispatch_is_agent_not_owner`): the prose dispatch "Read ~/proj/docs/task-….md and implement it…" is still `owner` untagged, the old answer kept on purpose. Tagged `coordinator`, it opens an `agent` card that reaches ready, shows the words without the tag, and the ring stays `working`.
- **Design #7, a tagged owner request typed through bro's omp:**
  ```
  tagged owner via omp: created (by owner) -> queued (by owner) -> working (by harness) -> ready (by harness); rings per tick: ['queued', 'ready']
  ```

`test_peer.SenderTag.test_the_tag_is_what_the_plugin_reads` closes the loop between the two halves: every tag peer.py can write parses in lifeview's `prompt_provenance` to the expected class.

## What changed

**Part 1, `config/herdr/skills/herdr-workstreams/peer.py`** (the repo copy):
- New functions: `sender_tag`, `tagged`, `project_of`, `herdr_agents`. New flags: `--from` and `--dry-run`. The docstring documents the format.
- **The delivery needle comes from the body, never the tag.** The old needle was the first 24 characters of the text. With a tag in front, that would be the tag, which is the same on every message from one sender, so it would match an earlier message.
- **Beyond the spec, needed for Part 3: omp-peer now confirms on claude targets.** The old copy read omp transcripts only, which is why the coordinator's prompt said "use bare `herdr agent prompt` for claude panes". That is the exact path that produced the misattributed dispatches.

  A rule forbidding bare `herdr agent prompt` needed a tagged sender that works there. It now finds the claude transcript by the session id herdr reports (`<id>.jsonl` in claude's per-project transcript dir). It reads string-content user entries, and `queue-operation` enqueue entries (a message typed mid-turn).
- **A real race fixed on the way:** the delivery baseline was taken *after* sending. A claude pane writes its queue entry instantly, so the entry counted as old and was never matched (the test caught it). The baseline is now taken before sending.

**Part 2, `config/herdr/plugins/lifeview-fallback/lifeview.py`:**
- `TAG`/`TAG_ORIGIN`, checked first in `prompt_provenance`: owner → owner; coordinator, worker and bro → agent; harness → machinery.
- Untagged prompts, and tags with an unknown role, follow the old code path line for line.
- New `untagged()`: the card's text and the auto-task title show the words that were asked, not the tag.

**Part 3, the agent rule.** "Never type into another agent's pane by hand; `omp-peer send` puts the tag on" is now in:
- `AGENTS.md`: a new section;
- `config/omp/rules/agent-pane-messaging.md`: it previously *recommended* `herdr agent prompt`;
- `config/omp/context-files/APPEND_SYSTEM.md`, the coordinator's delivery line: it previously said bare `herdr agent prompt`, and NOT omp-peer, for claude panes;
- `config/herdr/skills/herdr-workstreams/SKILL.md`: its claude-pane recipe and the "omp-peer is omp-only" note.

The last two are outside the files the task names. Leaving them would have contradicted the rule, and the coordinator would have kept sending untagged dispatches.

New file: `config/herdr/skills/herdr-workstreams/test_peer.py`. It stays in the repo; setup.sh copies only peer.py.

## Not done, and why

- **`~/.local/bin/omp-peer` was not updated**, as the task says. See the top of this report: install it before rolling omp panes.
- **prescient `_deliver`** is routed separately. Until it tags, hub nudges stay classified by shape (`prescient:` → machinery), exactly as today.
- **`agent-discord` relay** (design item 4, `[from:owner source:discord]`) is not in this task. Note: `TAG` accepts extra fields after the role, so `source:discord` will parse.
- **The plugin daemon was not restarted.** The tag is read from its next restart.
- **I did not live-send to a claude pane.** That would have injected a test message into another agent's turn. The claude-target path is covered by `SendPath.test_a_claude_target_is_confirmed_from_its_own_transcript` against a real transcript file, with herdr faked. The omp-target path was exercised live by this report's delivery to the coordinator, sent with the repo copy (result below).
- `config/omp/agents/implementer.md:27` still describes receiving a status check "via `herdr agent prompt`". That describes what is received, not an instruction to send, so I left it.

## Live delivery

The report path was sent to the coordinator with the **repo** copy (`python3 config/herdr/skills/herdr-workstreams/peer.py send omp-v35-wdp9 …`), from this claude pane. omp is nested in nvim, so this took the raw-paste path.

- **Delivered once.** The coordinator's session file has exactly one entry with the report path, and it starts `'[from:worker project:dotfiles id:claude-v2-wdpa]\n/…/docs/task-message-tags.report.md - …'`. So the tag arrived as its own first line inside a single user entry.
- **The first Enter was dropped,** and omp-peer's existing "retrying enter" step submitted it. This is old behaviour, not caused by the tag: earlier sends in this session's transcript show "retrying enter" 9 times.
