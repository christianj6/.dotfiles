# TASK: give claude panes a real config version, not the CLI's major

Owner: *"I'd like our claude panes to also have a version so that we can represent updates
to its global configurations. Like right now we have this V2, which isn't really
representing anything. Let's make it so I can tell that when everything is rolled out
that they're on the new version."*

## Current state (measured)

```
wD:p9   omp-in-nvim  v35*  omp-v35-wdp9      <- omp: real marker, /tmp/omp-config-versions/<pid>
wD:pA   claude       v<36  claude-v2-wdpa    <- claude: "v2" is the CLI's major version
wD:p7   omp-in-nvim  v36   omp-v36-wdp7
wD:pC   claude       v~36  claude-v2-wdpc
```

`config/herdr/plugins/claude-name/names.py:59`:

```python
def parse_major(version_output):     # "2.1.4" -> "2"
    match = re.match(r"\s*(\d+)\.", version_output)
```

So `claude-v2-wdpa` means "the claude CLI is 2.x" — it says **nothing** about
`config/claude/CLAUDE.md`, settings, hooks or the dotfiles version. Meanwhile omp panes
carry the real thing, which is why the two columns disagree and why "everything rolled"
is unverifiable on the Claude side.

## What to build

**A marker with the same meaning as omp's, so both columns read the same scale.**

omp does this in `config/omp/extensions/omp-config-version.ts`: at extension load it
writes `/tmp/omp-config-versions/<pid>` containing `config/omp/VERSION`, and omp-watch
maps pid → pane. Do the equivalent for claude:

1. **Write a marker at claude startup** containing the dotfiles config version for
   claude — i.e. `config/omp/VERSION` (one number for the whole harness, so the two
   kinds of pane are comparable) — at `/tmp/claude-config-versions/<pid>`.
   - Claude's `settings.json` already has a `PreToolUse` Bash hook, so hooks are a known
     mechanism here; use whichever startup hook claude offers (SessionStart or
     equivalent), and if none exists, say so rather than inventing one.
   - It must be written **at process start**, not per turn, or an idle pane shows
     nothing — the same lesson omp's extension documents.
2. **Name the pane from the marker**: `claude-v36-wdpa`, matching `omp-v36-wdp9`.
   - The CLI's major version is still useful — keep it somewhere (the roster detail or
     the tooltip), just not as the thing that looks like our config version.
   - Fall back to today's `claude-v<major>-<pane>` when there is no marker, so a pane
     that predates this change is visibly unversioned rather than wrong.
3. **`workspace-rollout` must read it.** Today it prints `v~36` for claude panes — an
   approximation it derives rather than reads. Replace that with the marker so the
   column is a fact: `v36` when current, `v35*` when stale, `-` when unknowable.

## Acceptance

1. A freshly started claude pane is named `claude-v<N>-<pane>` where N is
   `config/omp/VERSION` at process start, matching the omp panes beside it.
2. The marker file exists for a running pane and contains the number; a stale pane
   (started before a bump) keeps the old number until restarted.
3. `workspace-rollout --list` shows a **read** version for claude panes, not `v~36`, and
   marks stale ones with `*` exactly as it does omps.
4. After a full rollout of both pane kinds, every row shows the same N — that is the
   owner's actual requirement: one glance tells him everything is on the new version.
5. No marker → the fallback name, and the rollout column shows `-` rather than guessing.
6. Existing claude-name tests pass; add one for the marker path and one for the
   no-marker fallback.

## Rules
- This is dotfiles only: `config/herdr/plugins/claude-name/` and
  `config/herdr/bin/workspace-rollout`.
- Do not change `config/omp/VERSION`'s meaning — one number for the whole harness.
- Commit locally, do not push. Report what omp/claude startup hooks you found, and the
  before/after of `--list`.
