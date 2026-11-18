# REPORT: compaction not firing — stale omp processes restarted, and workspace-up now names them

Issue: `docs/issue-compaction-not-firing.md`.

## Headline

- **Restarted: prescient, bro and thor.** Each omp was restarted over the yarepl RPC path, on
  the same session it had open, and each live status bar changed from `…/?` (window unknown)
  to `…/1M`.
- **Their first decision line arrives with their next turn.** omp logs
  `Auto-compaction threshold decision` only after a turn, and none of the three has run one
  since the restart. `workspace-up` checks this from now on (see below).
- **Two more stale panes were missing from the table**, and I left both alone:
  - **`wD:p9`** (.dotfiles, the coordinator itself, pid 20944, started Nov 12 07:07):
    `contextWindow 0`, so it never compacts. It is off-limits to me.
  - **`wG:p6`** (ai-assisted-dev, pid 80155, started Nov 12 13:50): threshold 660000. It was
    not in the brief.
- **Durable fix:** `scripts/workspace-up` now checks every omp in a herdr pane against
  `config/omp`, names any stale one as "needs you", and exits 1.

## Job 1: the restarts

The same steps for each pane, using the rollout's own lua helper (`workspace-rollout`, the
`NV_LUA` block), run against that pane's nvim socket:

1. Gate: herdr `idle`, input box empty, the session quiet and ending on `assistant / stop`, and
   the session the omp has open is the newest for its cwd. `omp-last` resumes the newest, so
   this guarantees the same conversation comes back.
2. Typed `/exit` with `chansend` into job 3, checked the screen showed it, then sent Enter. omp
   exited within 2 s.
3. Confirmed the newest session had not changed, then ran `yarepl_start` (visible).

| pane | old pid → new pid | status bar before → after | session |
|---|---|---|---|
| bro `wD:p5` | 23795 → **83146** (17:33) | `205K/?` → `20.5%/1M` | same (`2026-10-26T11-02…`) |
| thor `wG:p1` | 24105 → **84434** (17:34) | `50.2%/1M` → `50.2%/1M` | same (`2026-10-06T07-33…`) |
| prescient `wD:p7` | 23590 → **452** (17:41) | `73K/?` → `7.3%/1M` | same (`2026-11-18T16-29…`) |

Notes:

- **Order:** prescient was mid-turn, so I restarted bro and thor first, then waited for
  prescient to go idle (`herdr agent wait`).
- **prescient's session file:** its `--resume` argument names the old 24 MB session, but
  `lsof` showed the process had moved to a new session at 16:29. That new file is the newest,
  so `omp-last` resumed the conversation that was actually live. I checked this before sending
  `/exit`.
- **thor:** it sits at about 502k tokens, so it should compact after its next turn (the
  threshold drops from 660k to 500k). That is the intended effect.
- **Log check:** `grep 'Auto-compaction threshold decision' omp.*.{452,83146,84434}.log`
  finds nothing yet, because no turn has run. Evidence so far:
  - each new process started after the config change (Nov 13 10:17);
  - each live status bar shows the 1M window, where it showed `?` before;
  - the same binary and config log `1000000 / 500000` in every pane started after Nov 13
    (topical, heinzel, knowledge-graph, market-research, telia).

  If any of the three logs something else, `workspace-up` names it.

## Job 2: `workspace-up` covers omp panes

`scripts/workspace-up`: a new section after the service pieces.

- **Which processes:** every interactive omp whose environment carries a `HERDR_PANE_ID`. It
  uses `ps -E` and the cwd from `lsof`, and skips `omp -p`.
- **The truth for each pane is the process's own log:** the newest
  `Auto-compaction threshold decision` in `~/.omp/logs/omp.*.<pid>.log`. Logs dated before the
  process started are ignored, in case the pid was recycled.
- **Verdict:**
  - `contextWindow 0` → STALE: never compacts.
  - `thresholdTokens` ≠ `min(config thresholdTokens, window − 1)` → STALE: `threshold X vs
    config Y`.
  - No turn logged yet → STALE only if the process started before the newest mtime of
    `config.yml` or `models.yml`; otherwise ok.
- **A stale pane is named and counted:** one line per pane, `N omp stale` in the summary, and
  an entry in "need you" with the remedy (`/exit`, then `ctrl+a`). That makes the exit code 1
  (acceptance 3).
- **Report only, never a restart:** an agent's REPL may be mid-turn or hold typed input, and a
  safe restart needs the gates from Job 1. That is a judgement call, not something for a
  startup hook. At herdr start the panes come up empty anyway, so there is nothing to check
  then.
- **Scope:** `--only omp` runs just this section, and `--only <service>` skips it. The
  restore hook only appends the output to `restore.log`, so nothing that parses it breaks.

Live run (`python3 scripts/workspace-up --dry-run --only omp`, after the restarts):

```
omp w5:p1R   topical          pid 49506  up 4d   ok: window 1000000, threshold 500000
omp w5:p1T   heinzel          pid 75495  up 3d   ok: window 1000000, threshold 500000
omp wD:p5    bro              pid 83146  up 8m   ok: no turn logged yet, started after the config
omp wD:p7    prescient        pid 452    up 17s  ok: no turn logged yet, started after the config
omp wD:p9    .dotfiles        pid 20944  up 6d   STALE: contextWindow 0: never compacts (config 500000)
omp wG:p1    thor-voiceai     pid 84434  up 7m   ok: no turn logged yet, started after the config
omp wG:p6    ai-assisted-dev  pid 80155  up 6d   STALE: threshold 660000 vs config 500000
omp wG:pC    knowledge-graph  pid 4499   up 2d   ok: window 1000000, threshold 500000
omp wG:pE    market-research  pid 37479  up 2d   ok: window 1000000, threshold 500000
omp wG:pG    telia-sms-fraud  pid 14852  up 1d   ok: window 1000000, threshold 500000
workspace: … 2 omp stale, 2 need you - omp wD:p9 (.dotfiles): contextWindow 0: never compacts … ; omp wG:p6 (ai-assisted-dev): threshold 660000 vs config 500000 …
exit 1
```

Before the restarts, the same run named prescient as well: `3 omp stale`. That covers
acceptance 2: a stale pane is named, not tolerated.

### Tests

`python3 scripts/test_workspace_up.py`: 17 tests, all passing. The 8 new ones are in
`OmpPanes`:

- window 0 is stale and gives exit 1;
- the old 660k is stale;
- a matching pane is ok;
- a threshold clamped to a small window is ok;
- with no turn logged, the verdict comes from start time versus config mtime;
- the decision is read from the newest line for that pid, ignoring other pids and recycled
  pids' old logs;
- the config threshold is read from the committed `config.yml`;
- a services-only run has no omp section.

## Open

- **`wD:p9`** (the coordinator's own omp) never compacts until it restarts. It cannot run
  `/exit` on itself from inside a turn, so the owner, or the coordinator between turns, has to
  run `/exit` then `ctrl+a` in that pane.
- **`wG:p6`** (ai-assisted-dev): restarting it needs your go-ahead; it was outside the brief.
- **Acceptance 1:** bro, thor and prescient have not logged their first decision yet.
  `workspace-up --only omp` shows the verdict once they do.

## Untouched

- No claude pane, and not `wD:p9`.
- `config/claude/settings.json`: an uncommitted change I did not make.
