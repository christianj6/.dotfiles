# Handoff verification: omp and claude in one project

Run 2026-11-02 on herdr 0.9.5 and omp v17.3.4, in a throwaway workspace that
was closed afterwards. Paths are shown with `$TMPDIR` and `~`.

## Result

The file-only loop works: spec delivered, work done, report written, path sent
back, and the coordinator read the report and checked the output itself. The
working invocations are:

| Direction | Command | Confirmation |
| --- | --- | --- |
| omp to claude | `herdr agent prompt <claude-name> "<one line + path>"` | Exit 0 means fired; check with `herdr agent read` |
| claude to omp | `omp-peer send <omp-name> "<path + one line>"` | Exit 0, `delivered <session-file>` |

`omp-peer send` to a claude pane does NOT work as a confirmed path. It delivers
the message and then exits 2.

## Setup

    herdr workspace create --cwd "$HOME" --label handoff-scratch --no-focus
    herdr pane split <root-pane> --direction right --no-focus
    herdr pane run <pane> "cd <project> && omp"
    herdr pane run <pane> "cd <project> && claude --permission-mode acceptEdits --allowedTools 'Bash(omp-peer:*)'"
    herdr agent rename <pane> <name>

Each spec asked claude to create a file holding `ok`, write a report next to
the spec, and send the report path to the omp pane. The sends to claude were
run from the implementing session rather than typed by the scratch omp; the
command is the same. The return sends were run by the scratch claude.

## Run 1: both agents in `$TMPDIR/handoff-scratch`

Spec-named invocation, omp to claude:

    $ omp-peer send scratch-claude "read $TMPDIR/handoff-scratch/handoff-smoke-test.md and do it; report per the spec"
    omp-peer: waiting for delivery (timeout 30s) ...
    omp-peer: delivery not seen within 30s

The message landed anyway: claude's transcript held it, claude created the file
(`xxd`: `6f6b`) and wrote the report.

Return path, run by the scratch claude:

    $ omp-peer send scratch-omp "report: <path> - smoke test done" --no-guard
    Exit code 2
    omp-peer: waiting for delivery (timeout 30s) ...
    omp-peer: delivery not seen within 30s

This also landed. The omp transcript shows it as a user entry, and omp read the
report and checked the file (`od`: `6f 6b`, `wc -c`: 2).

## Run 2: both agents in `~/handoff-scratch`

This matches a real project: omp and claude share a cwd under `$HOME`.

Probe, `omp-peer` to claude:

    $ omp-peer send scratch-claude-2 "probe-a: reply with the single word pong"
    omp-peer: waiting for delivery (timeout 30s) ...
    omp-peer: delivery not seen within 30s
    exit=2

Claude had answered `pong` within a second.

Spec delivery, the working invocation:

    $ herdr agent prompt scratch-claude-2 "read ~/handoff-scratch/handoff-home-test.md and do it; report per the spec"
    exit=0
    {"id":"cli:agent:prompt","result":{"agent":{"agent":"claude", ... "name":"scratch-claude-2", ...},"type":"agent_prompted"}}

Return path, run by the scratch claude:

    $ omp-peer send scratch-omp-2 "report: ~/handoff-scratch/handoff-home-test.report.md - home test done" --no-guard
    omp-peer: waiting for delivery (timeout 30s) ...
    delivered ~/.omp/agent/sessions/-handoff-scratch/2026-11-02T06-44-07-840Z_01a19b00-4220-7000-8dea-0b179b4e84ec.jsonl

The scratch omp then read the report and verified the output (`wc -c`: 2,
`od -c`: `o k`). `xxd` from outside the pair: `6f6b`.

## What failed, and why

- **`omp-peer` to a claude pane exits 2 after delivering.** It only polls
  `~/.omp/agent/sessions`, so claude's transcript is never checked. Resending
  on that exit code duplicates the task.
- **`omp-peer` to an omp pane outside `$HOME` exits 2 after delivering.** omp
  filed the `$TMPDIR` session under `-tmp-handoff-scratch`, a key
  `candidate_keys()` does not produce. Under `$HOME` it confirms correctly.
- **A spec writing outside the project stalls.** In run 2 the write to `/tmp`
  stopped claude on an approval dialog for about two minutes until it was
  approved by hand. Nothing reaches the coordinator; herdr reports the agent as
  `blocked`, so `herdr agent list` shows it.
- **A fresh directory stops on claude's trust prompt.** The default option is
  "No, exit", so an unattended Enter closes claude. It needs `down`, then
  `enter`.
- **A fresh omp has no session file until its first message.** Globbing the
  session dir before then finds nothing.

## Not tested

- An omp nested in nvim's ctrl-a REPL, which is the owner's normal setup. Both
  omp panes here were standalone, and the return sends used `--no-guard`.
- The 90-second "stuck peer" guidance in the workstreams skill.
