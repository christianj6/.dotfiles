# Post-restart coordinator round (2026-11-12)

Owner rebooted. Before handing off the automation work, I checked what the reboot actually
left dead — and it was worse than the panes suggested.

## What the reboot left broken

| piece | state after reboot | evidence |
|---|---|---|
| all 10 herdr panes | **empty** — no nvim, no omp, no claude | `pane list`: everything `agent_status: unknown` |
| **prescient 8765** | **down** | `workspace-up` started it (pid 36122) |
| **bro serve 8766** | **down** | `workspace-up` started it (pid 36180) |
| lifeview daemon | up, but 15h older than its code | `workspace-up`: `code 15h old` |
| discord bot | up, 14h older than its code | same |

So the panes existing was cosmetic: **three of four services were down or stale**, and
`scripts/workspace-up` — built yesterday — started prescient and bro and reported
`0 unhealthy, 0 need you`. That is the tool doing exactly what it was built for.

## The coordinator round

Asked each system agent the same three questions: is your service healthy, did your session
survive, is anything missing. Facts only, nothing started without saying so.

| agent | service | session | gaps |
|---|---|---|---|
| **prescient** `omp-v36-wdp7` | 8765 `/api/health` 200, strict + guarded | **same conversation, same context** | none; repo `4483b1a` clean, 12 commits local |
| **heinzel** `omp-v36-w5p1d` | 8765 healthy, bro `ok:true` | **same conversation** — full prior context (haus feel round, the auto-task false-pass correction) | none: gpu and mic free, no demo/bench/playtest running |
| **thor** `omp-v36-wgp1` | pane survived | **session intact**, nothing was in flight | docker daemon + AWS SSO token down (thor11), **neither needed yet**; started nothing |
| **bro** `omp-v36-wdp5` | 8766 `/health` 200 | live | not reported back in time |

**Every coordinator reported the same thing: the panes came back and their conversations
survived.** That is the good news, and it is a real property of the setup — herdr restored
the session identity even though nothing was running in the panes.

## The one regression I caused

`w5:p1G` (archi-skill) **existed when I started** and was gone by the time I finished. I had
started nvim+omp in it during the restore pass; it is now absent from both `pane list` and
`agent list`. Most likely one of my `:qa` attempts in that pane closed it — the same
nvim-is-the-root-process trap that deleted `wD:pA` and `wD:pH`. **Not yet replaced**, and
recorded rather than quietly dropped.

## The shape right now

```
wD:p9   omp     .dotfiles      ┐ nvim+omp left
wD:pJ   claude  .dotfiles      ┘ claude right   <- restored, working
wD:p7   omp     prescient
wD:pC   claude  prescient      <- correct shape
wD:p5   omp     bro
wD:p6   claude  bro            <- correct shape
w5:p1D  omp     heinzel
w5:p1A  claude  heinzel        <- correct shape
wG:p1   omp     thor-voiceai   <- no claude pane (was never there)
```

## For the handoff: what "just type herdr and everything is up" now requires

Three separate gaps, and the automation must close all three:

1. **Panes come back empty.** The `.zshrc` `exec nvim` makes them nvim, which is right for the
   left pane and wrong for the right one — and `herdr agent start` needs a **shell** pane, so
   the right pane must be created with `--env HERDR_NO_NVIM=1`.
2. **Services do not start.** prescient, bro and the two daemons need `workspace-up` run — it
   exists, is idempotent, and worked; nothing invokes it at herdr start.
3. **`archi-skill` has no claude pane** and its omp pane is now gone.

The known-good recipe for one right-hand pane, verified live today:

```
herdr pane split --pane <left> --direction right --cwd <project> --env HERDR_NO_NVIM=1
herdr agent start claude-v36-<pane> --kind claude --pane <newpane>
```
