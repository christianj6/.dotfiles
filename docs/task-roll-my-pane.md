# TASK: roll my own pane (wD:p9) to v35 — the only pane left

Everything else is already on v35: prescient (wD:t3), bro (wD:t2), and my Claude (wD:pA). Only my omp pane (wD:p9, omp-v25-wdp9) is stale, because `workspace-rollout` refuses to restart the pane that runs it.

Run, from ~/.dotfiles:

    config/herdr/bin/workspace-rollout wD:t4

It will SKIP wD:p9 for that reason. You must do the restart yourself:

1. Wait for this session to be idle — you cannot roll it while I am mid-turn, and I am about to go quiet.
2. In pane wD:p9 (MY pane, not yours): send `/exit` via nvim RPC chansend (it is omp-in-nvim, a yarepl REPL opened with ctrl+a) and let yarepl close the buffer.
3. Restart through yarepl so ctrl+a keeps working, resuming THIS session — the newest omp session for ~/.dotfiles, which is `2026-10-03T03-42-34-976Z_01a0ffdb-43e0-7000-a46c-aaffc847c453.jsonl`. Use omp-last (it resumes the newest for nvim's cwd) and VERIFY that newest one is the file named above before you send it. If it is not, STOP and report — do not resume the wrong conversation.
4. Confirm afterwards: `config/herdr/bin/workspace-rollout --list` shows wD:p9 at v35.

Rules:
- Do not restart wD:pA (yours) again, prescient, bro, thor, heinzel or marketing.
- If anything is ambiguous — the newest session is not the one named, yarepl does not come back, or omp resumes a different conversation — STOP and report. Losing this conversation is worse than staying on v25.
- Report: the version shown for wD:p9, whether the resumed session matched, and anything that looked wrong.
