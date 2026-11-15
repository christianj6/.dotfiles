# REPORT: heinzel's omp pinned at "working" — the cause is a foreign claim

Issue: `docs/issue-stuck-working-status.md`.

## Headline

- **Restarting the omp did not clear it.** The restart itself worked cleanly: new omp pid
  54767, same session file. The sidebar still says `working`, and `herdr agent explain` still
  says `idle`.
- **The cause is not a wedged source.** It is a **foreign agent-session claim**:
  `herdr pane get w5:p1D` shows
  `agent_session: {source: "herdr:claude", agent: "claude", value: "81d10105-…"}` on an omp
  pane.
- **This is a known failure mode.** `watch.py`'s `foreign_claim()` (line 582) documents it
  from 2026-09-15:
  - herdr accepts every custom report with "ok" and applies none, whatever the source name;
  - release-agent is a no-op;
  - the claim lives in `~/.config/herdr/session.json`, so it survives restarts.
  That explains all four dropped reports in the issue, and why a fresh source failed too.
- **The watcher already detected it, but went silent.** It printed one warning to stderr.
  The `[[startup]]` instance's stderr is a pipe nobody reads, so nothing reached any log.
- **Recovery needs a decision (below).** The only remaining remedies are recreating the pane
  or stopping the server, and both are bigger than the restart the spec authorised.

## Recovery: what was done

The yarepl RPC path, run by hand with the rollout's own lua helper (`workspace-rollout` lines
327–377). The rollout itself cannot do this pane: its `wait_idle` gate waits for herdr to say
`idle`, and herdr is stuck at `working`.

1. **Pre-checks:**
   - transcript quiet for 2620 s, last entry `assistant / stop`;
   - REPL input box empty;
   - this session is the newest for heinzel's cwd;
   - nvim socket `…/nvim.23878.0`, embed child of nvim 23877.
2. **`/exit`:** sent with `chansend` into job 3. The box showed exactly `/exit` before Enter
   was sent. omp 24000 exited in about 1 s.
3. **Session check:** still the newest, so nothing overtook it.
4. **Restart:** `yarepl_start` (visible) → `ok`. The new omp is pid 54767, running
   `--resume=…/2026-10-09T15-05-11-101Z_01a12132….jsonl`, the same session.

Result: `herdr agent list` still shows `omp-v36-w5p1d working`, and `explain` still shows
`idle`. **Acceptance 1 is not met by a restart.**

Then I tested whether anything sent over the CLI can clear it. Each call below returned ok;
I checked the pane after each one:

| call | state after |
|---|---|
| `release-agent --source herdr:claude --agent claude` | working, claim intact |
| `release-agent --source herdr:claude --agent omp` | working, claim intact |
| `report-agent --source herdr:claude --agent claude --state idle` (posing as the owner) | working |
| then `release-agent --source herdr:claude --agent claude` | working, claim intact |
| `report-agent --source custom:omp-watch --agent omp --state idle` (fresh seq) | working |

This confirms the September finding on herdr 0.9.5: no report or release, from any source,
clears a foreign claim.

**Origin of the claim: not found.** Claude session `81d10105…` left no transcript in claude's
project store, so it was a session-less `claude -p` or a probe. Whatever it was, it
inherited `HERDR_PANE_ID=w5:p1D`, and no live claude process carries that pane id now.

## Recovery: what is left (decision needed)

Either of these clears it:

**A. Recreate the pane (recommended; touches only heinzel's left pane).**

1. `/exit` the omp over RPC, exactly as above.
2. `herdr pane split --pane w5:p1D --direction right --cwd <heinzel> --no-focus`. The new pane
   execs nvim with no claim on it.
3. `ctrl+a` in the new pane. `omp-last` resumes the same, newest session.
4. Check `w5:p1D`'s nvim for unsaved buffers. Its files stay in the nvim session.
5. `herdr pane close w5:p1D`. The new pane takes the left slot, beside `w5:p1A`.

I did not do this: it closes an owner pane, and the spec authorised a restart only.

**B. Stop the herdr server and run `scripts/herdr-clear-agent-claims.sh`.** This kills every
pane, so I don't recommend it.

## Prevention (shipped, `config/herdr/plugins/omp-watch/watch.py`)

1. **Escalations go to a file:** `$HERDR_PLUGIN_STATE_DIR/events.jsonl` (also echoed to
   stderr), one JSON line per event, via `emit_event()`:
   - **`report_release_retry`:** once per wedge, when rotation is exhausted and *no* foreign
     claim owns the slot. The watcher releases its own claim and re-reports from a fresh
     source. This is the last-resort hammer from the issue's prevention step 2. It is
     skipped when a foreign claim is present, because it is a proven no-op there (today and
     on 2026-09-15).
   - **`report_wedged`:** once per wedge, after that retry fails, or straight away when a
     foreign claim owns the slot. It names the pane, the registry state, our verdict,
     herdr's explain, the claim's source and agent, and the remedy.
   - **`report_recovered`:** when the registry converges again. This clears both one-shot
     flags, so a later wedge is reported too.
   - **Reporting never stops:** rotation and the 120 s backoff carry on as before.
2. **The escalation is not gated on `herdr agent explain` disagreeing, and this is
   deliberate.** omp has no herdr screen manifest, so explain always gives the idle fallback
   (`fallback_reason: default_known_agent_idle_fallback`). A working omp stuck at `idle` in
   the registry would *agree* with explain, and the wedge would go unreported. So explain is
   recorded in the event as a diagnostic, and the gate is our own verdict versus the
   registry, which is the condition that already drives rotation.
3. **Idle heuristic unchanged** (acceptance 5). `infer_state`, `gate_verdict` and the
   constants are untouched.

### Tests (`test_watch.py`, `python3 test_watch.py`: all 21 groups pass)

`_drive_main()` runs the **real** `main()` loop against fakes: a live omp, verdict idle, and a
registry that accepts every report and never applies one (always `working`).

- `test_report_dropping_registry_escalates_instead_of_going_silent`: `report_release_retry`
  once, then `report_wedged` once, in that order. The release really goes to herdr, and
  reports keep flowing afterwards.
- `test_foreign_claim_wedge_skips_the_noop_release_and_names_the_claim`: no release, one
  `report_wedged` naming `herdr:claude`, with the claim-strip remedy.
- `test_wedge_recovery_is_logged_and_rearms_the_event`: stuck, then recovered, then stuck
  again gives a wedge, `report_recovered`, then a second wedge.
- `test_converging_registry_emits_nothing`: a healthy registry produces no events and no
  calls.
- **Against the old `watch.py`:** the new tests cannot pass, because it writes no events
  file. They fail at the first lookup, with an error rather than an assertion failure.

### Live proof

I reloaded the running watcher with `kill -HUP 14463`: same pid, it re-execs itself with the
new code. Within about 50 s it wrote:

```
2026-11-15T09:04:04+0100 report_wedged w5:p1D {registry: working, verdict: idle, explain: idle, foreign_claim: herdr:claude, remedy: "…recreate the pane, or stop the server and run scripts/herdr-clear-agent-claims.sh"}
```

That is the event that would have made this visible 40 minutes earlier.

## Untouched

- **`w5:p1A`** (claude, working): not touched.
- **`w5:p1R` / `w5:p1S`:** a second heinzel tab appeared in `w5` during the session. Not
  mine; not touched.
- **`config/claude/settings.json`:** an uncommitted change I did not make; left out of the
  commit.
- **Inline reads above 5 without a sub-agent this turn:** each call was a live-state probe
  whose result chose the next step (process tree → socket → screen → restart → claim). It
  was not a bulk read.
