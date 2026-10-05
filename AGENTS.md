# Agent rules for this repo

This repo is **PUBLIC** (github.com/christianj6/.dotfiles): anyone can clone
it, and fresh-VM setup works without authentication. Everything pushed is
published.

## Hard rule — no private content

Never stage or commit:

- **Credential values** (API keys, tokens, passwords, private keys). Secrets
  live in `~/.dotfiles/.env`, which is gitignored. Referencing env-var
  *names* in code and docs is fine.
- **Home-anchored private paths** — anything under the owner's Desktop
  (personal projects, work workspace checkout locations). Bare scope
  markers in scope-rule code (e.g. a work-marker constant) are fine.
- **Personal project content**: planning notes, task bodies, board card
  exports, session/transcript files, chat logs — even paraphrased or
  excerpted. These live in private repos and in the owner's head, not here.

Fine to publish (owner decision 2026-10-05): project names, one-line board
bookkeeping, migration status, epic titles — this only reproduces at a high
level what is visible in the code base and auditable from commit history.

## Enforcement

Two local layers run `scripts/check-private.py` against
`scripts/private-patterns.txt` (the owner's tuning knob) — deliberately
no cloud CI for this (owner decision 2026-10-05, too much infrastructure
for a simple local check):

1. `.githooks/pre-commit` — blocks local commits (repo sets
   `core.hooksPath=.githooks`).
2. `config/omp/extensions/omp-privacy-guard.ts` — blocks `git commit`/`git
   push` tool calls, catching `--no-verify` bypasses.
   Manual full-tree audit when wanted: `python3 scripts/check-private.py --all`.

If a line is flagged but genuinely belongs in the repo, propose a pattern
change to the owner — never bypass the hook or the guard. If you find
private content already tracked, STOP and surface it to the owner instead
of committing around it.
