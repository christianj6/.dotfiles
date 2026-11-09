# TASK: roll my own pane (wD:p9) to v36 — the last one

Everything else is already on **v36**: prescient (wD:p7, wD:pC), bro (wD:p5, wD:p6),
thor (wG:p1), marketing (wG:p3), heinzel (w5:p1D, w5:p1A), and my Claude (wD:pA).

Only **`wD:p9` (omp-v35-wdp9, my pane)** is stale, because `workspace-rollout` refuses
to restart the pane that runs it:

```
wD:p9    omp-in-nvim    v35*    working    omp-v35-wdp9    ~/.dotfiles    this pane runs the rollout
```

## Do this

From `~/.dotfiles`:

1. **Wait until my pane is idle.** I will be quiet after this turn. Do not type into a
   pane that is mid-turn.
2. In **pane `wD:p9`** (MINE, not yours): send `/exit` via nvim RPC chansend — it is an
   omp-in-nvim, a yarepl REPL opened with `ctrl+a` — and let yarepl close the buffer.
3. Restart it **through yarepl** so `ctrl+a` keeps working, resuming THIS session:

   ```
   ~/.omp/agent/sessions/-.dotfiles/2026-10-03T03-42-34-976Z_01a0ffdb-43e0-7000-a46c-aaffc847c453.jsonl
   ```

   `omp-last` resumes the newest session for nvim's cwd. **Verify the newest session for
   `~/.dotfiles` is that exact file before you send it.** If it is not, STOP and report —
   resuming the wrong conversation is worse than staying on v35.
4. Confirm afterwards:

   ```
   config/herdr/bin/workspace-rollout --list | grep wD:p9
   ```

   It must read **v36** with no `*`, and the pane name must become `omp-v36-wdp9`.

## Rules

- Do **not** restart any other pane. Everything else is already v36 and restarting it
  again would interrupt work for nothing.
- `workspace-rollout wD:t4` will SKIP `wD:p9` (it is the pane running the rollout) — that
  is expected; the restart is yours to do by hand as above.
- If anything is ambiguous — the newest session is not the named file, yarepl does not
  come back, or omp resumes a different conversation — **STOP and report**. Losing this
  conversation is worse than staying on v35.
- Commit nothing. This task changes no files; it restarts one pane.

## Report

The version `--list` shows for `wD:p9` after the restart, whether the resumed session
matched the named file, and anything that looked wrong.
