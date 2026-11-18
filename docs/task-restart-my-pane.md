# TASK: restart the coordinator's pane (wD:p9) so its omp picks up compaction 500k

Owner: *"tell your claude to restart your pane."*

This is the last stale pane. `scripts/workspace-up` reports it:

```
omp wD:p9  .dotfiles  pid 20944  up 6d  STALE: contextWindow 0: never compacts (config 500000)
```

## Exact facts (verified, do not re-derive)

| what | value |
|---|---|
| pane | **`wD:p9`**, tab `wD:t4`, cwd `~/.dotfiles` |
| omp pid | **20944** (`bun …/omp --resume=…`) |
| its nvim embed | **20411** (`nvim --embed`) |
| its nvim | **14280** |
| session file to resume | `~/.omp/agent/sessions/-.dotfiles/2026-10-03T03-42-34-976Z_01a0ffdb-43e0-7000-a46c-aaffc847c453.jsonl` |

The process chain is `herdr 14277 → herdr server 14278 → nvim 14280 → nvim --embed 20411 → omp 20944`.

## How

Use the same path `workspace-rollout` uses for an omp-in-nvim pane, and **verify the session
before sending**:

1. `/exit` into the REPL via nvim RPC chansend (the yarepl terminal for `#pi#1` in pane `wD:p9`).
   Do **not** type `:q`/`:qa` — in this pane those go to the REPL and, worse, quitting nvim
   destroys the pane (nvim is the pane's root process in a `.conda-env` project).
2. Restart through yarepl: `yarepl_start` with the REPL command `omp-last` (resumes the newest
   session for nvim's cwd) — **first confirm the newest session for `~/.dotfiles` is exactly the
   file named above**. If it is not, STOP and report; resuming the wrong conversation is worse
   than leaving the pane stale.
3. Confirm afterwards:
   - `scripts/workspace-up 2>&1 | grep 'wD:p9'` → must say `ok: window 1000000, threshold 500000`
   - or read the new pid's log: `contextWindow:1000000, thresholdTokens:500000`
   - the pane still shows `TERMINAL #pi#1` with cwd `~/.dotfiles`

## Rules

- **Only `wD:p9`.** Do not touch any other pane. `wG:p6` (ai-assisted-dev) is also stale and is
  *not* yours to restart — leave it named in the summary.
- Do not close or recreate the pane; restart only its omp. The pane carries no foreign claim
  (verified when heinzel's was fixed), so a plain REPL restart is enough.
- If anything is ambiguous — the newest session is not the named file, yarepl does not come back,
  or omp resumes a different conversation — STOP and report rather than improvising.
- Commit nothing. This changes no files.

## Report

The threshold the pane reports after the restart, whether the resumed session matched the named
file, and `workspace-up`'s line for `wD:p9`.
