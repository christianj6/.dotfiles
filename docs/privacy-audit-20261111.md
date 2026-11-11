# Git + privacy audit (2026-11-11)

Owner: *"make sure git is up to date and no private data is leaked."*

## Push state — all three repo in sync

| repo | visibility | before | after |
|---|---|---|---|
| dotfiles | **PUBLIC** | 15 ahead | pushed (`3fe0fe9`) |
| prescient | private (404) | 40 ahead | pushed |
| bro | private (404) | 219 ahead | pushed |

## Privacy: what was checked, and what it found

**dotfiles is the only public repo**, so that is where the scan matters. Two passes:

1. `scripts/check-private.py --all` on the tracked tree → **clean**.
2. Every added line of every unpushed commit (`git diff origin/main..HEAD | grep '^+'`) →
   **0 hits** for home paths, Trello/API keys, `sk-` tokens, private-key headers. Commit
   *messages* also scanned: clean.

Prescient and bro were scanned the same way. Prescient: 0 hits. Bro: 23 hits — **all home
paths in its own docs and shell config** (a home-anchored projects-dir default path,
a tmux status-right, a vim autocmd, and prose telling agents where projects live). Bro is a
**private** repo (GitHub API returns 404), those paths name the owner's own layout, and they
were already in its history — not a leak, and not this repo's rule.

## Two real findings, both fixed before any push

**1. Nine symlink loops in the working tree.** `setup.sh` at some point ran an `ln -sfn` that
landed *inside* an existing directory, producing self-references:

```
config/omp/skills/research/research -> …/config/omp/skills/research
```

…for nine skills (codebase-design, domain-modeling, grill-with-docs, grilling,
improve-codebase-architecture, issue-tracker-trello, prototype, research, wayfinder).
**All nine were untracked** — `git ls-files` shows only `SKILL.md` under each — so nothing had
ever been committed and nothing reached a remote. Removed. Worth a look at `setup.sh` if it
recurs: the repo-side `ln` lines look correct (they target `~/.omp/agent/skills/…`), so this
was a one-off manual run, not the script.

**2. An inbound cross-project report was about to be committed.** `HARNESS-autotask-bug.md`
(heinzel's) arrived in the repo root, untracked and **not gitignored**. The guard refused it:

```
HARNESS-autotask-bug.md:88: a home-anchored path into heinzel's release docs
  private content must not land in this PUBLIC repo
```

That is the guard doing its job on a real file. Fixed structurally: inbound reports now go to
`.inbox/`, which is gitignored — so the next report cannot be swept in by a `git add -A`.

## One correction I made to my own housekeeping

Moving the inbound files, I also moved `lifeview-autotask-gap.answer.md` — which was
**already tracked and committed**. That would have been an unintended deletion of published
content. Caught it in the same command's output and restored from git. Inbound-only is the
rule; already-tracked is not inbox.

## Residual

- `docs/agent-pane-messaging-20261029.md` remains untracked in the repo root. It is a
  scratch note, not inbound; leaving it and saying so rather than silently deleting.
- The privacy guard is **three local layers with no CI** (owner's 2026-10-05 decision), so a
  `--no-verify` + push of *already-committed* content is caught only by `pre-push`. Verified
  earlier today that it does catch a mid-history leak.
