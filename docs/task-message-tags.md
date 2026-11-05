# TASK: put the sender's tag on every agent-to-agent message

Repo: ~/.dotfiles. Design: `docs/design-message-tags.md` — read it first.
Owner's instruction: *"Get Claude involved and let's add the missing pieces."*

## The problem this closes

Every agent-to-agent message in this workspace is typed into a pane as plain
text, and a pane record is `{"content": …, "role": "user"}` — **no sender**.
So the harness guesses provenance from prose, and guesses wrong: two of my
dispatches to dotfiles' Claude were recorded `origin: owner`
(`tk-35a1ddfb2295`, `tk-01591d8d2d41`) when they were mine.

**Four senders, all ours.** The sender is known at the moment of sending, so write
it into the text.

## Part 1 — `omp-peer send` (dotfiles, yours)

Files: `config/herdr/skills/herdr-workstreams/peer.py` (the versioned source;
`setup.sh:322` copies it to `~/.local/bin/omp-peer`, so **edit the repo copy**, and
do not touch `~/.local/bin/omp-peer`).

Prepend exactly one line, unless the caller already supplied a tag:

```
[from:<role> project:<project> id:<name>]
```

- `role`: `coordinator` when the sender is an omp pane, `worker` when it is a claude
  pane, `owner` when `--from owner` is given. Determine the sender's own pane with
  `herdr agent list` matching the current pane id — the same lookup the script
  already does for the target.
- `project`: the sender's cwd basename, matching how the board names projects
  (`.dotfiles` → `dotfiles`).
- `id`: the sender's herdr agent name.
- `--from <role>` overrides the role (the owner relaying by hand).
- **Never** double-tag: if the text already starts with `[from:`, send it unchanged.

## Part 2 — the plugin must read the tag FIRST

File: `config/herdr/plugins/lifeview-fallback/lifeview.py`, in `prompt_provenance`.

```python
TAG = re.compile(r"^\s*\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]")
```

- A tag wins over **every** shape rule. `[from:owner]` beats `Round N:`, beats a spec
  path, beats everything — the owner's words can look like anything.
- `coordinator` / `worker` → `agent`.
- `harness` → `machinery` (no card: this is what keeps the 2026-11-03 loop shut).
- `bro` → `agent`.
- Untagged → today's behaviour, unchanged: machinery shapes, then the comms shapes,
  then `owner`.

## Part 3 — agent rule

Add to `AGENTS.md` (or the messaging rule, `config/omp/rules/agent-pane-messaging.md`):
**never type into another agent's pane by hand — `omp-peer send` puts the tag on.**
Bare `herdr agent prompt` produces an untagged message that can be misattributed.

## Acceptance — show, do not describe

1. `omp-peer send` prefixes `[from:coordinator project:dotfiles id:<name>]` when sent
   from an omp pane; `--from owner` yields `[from:owner …]`.
2. Text that already starts with `[from:` is sent unchanged (no double tag).
3. `prompt_provenance` reads the tag before any shape rule: a tagged
   `[from:owner] Round 25: …` is **owner**; an untagged `Round 25: …` is **agent**.
4. `[from:harness]` → machinery → no card.
5. `[from:coordinator]` and `[from:worker]` → `agent`.
6. Every existing untagged case in the test file still passes unchanged.
7. Run `python3 config/herdr/plugins/lifeview-fallback/test_lifeview.py` and
   `python3 -m pytest tests/` if that applies to the peer script. No project-wide suites.

## Rules
- Commit locally, **do not push**, cite `tk-b32624856c72`.
- Do not change prescient — its `_deliver` half is routed separately.
- Report: the tag format you settled on, the 7 acceptance results, and anything you
  chose not to do.
