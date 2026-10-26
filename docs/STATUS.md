# Status: .dotfiles
Updated: 2026-10-26 12:23 (Europe/Berlin)

## Now
- Nothing in flight — all delegated work has landed and is pushed. Standing by.

## Next
- Roll the remaining stale panes onto config v24 when convenient (dotfiles tab, heinzel tab, the Thor demo-worktree tab) — one `workspace-rollout <tab>` each.
- Optional: also scrub the "#pi#1" buffer label from NvChad's tabline/statusline (the float itself is already clean).

## Waiting on the owner
- One uncommitted line in `config/omp/config.yml`: the `task` model role was switched to `anthropic/claude-sonnet-5`. Commit it (subagents reroute to Sonnet) or revert it — your call.
- Two omp panes (prescient `w5:p14`, topical `w5:p16`) are `NEEDS-MANUAL`: their nvim sat on a modal prompt during the rollout. Dismiss the prompt, then run `workspace-rollout w5:tN --only w5:p14` and `workspace-rollout w5:tP --only w5:p16`.

## Blocked
- Nothing.

## Recently landed
- `workspace-rollout`: one command brings a project tab's agent panes to the latest config version at their next idle point, resuming each session — with dry-run, per-pane targeting, and self-detection of the herdr registry-wedge failure mode.
- Config v24 is live: Thor verified end-to-end (session resumed, sidebar state accurate); prescient and topical claude panes rolled.
- Discord replies now work mid-typing: the relay focuses the omp REPL over nvim RPC instead of the fragile ctrl+a dance; `omp-peer` got the same upgrade, and the running bot already has it.
- Trello `Maps` list deprecated — every project's standing context now lives in its own repo (`docs/DEV_BOARD.md`).
- Privacy guardrail on this public repo: pre-commit hook + agent extension + `AGENTS.md` policy, all local (no cloud CI, per owner).
- terminal-browser disabled pending a performance rethink; root-cause analysis in `docs/terminal-browser-perf.md`.
- omp REPL float: wider (70% width, 90-col floor) and the `#pi#1` label removed from the float.
- `rea` MCP server moved off global registration — project-scoped on demand only (decomp tasks).
