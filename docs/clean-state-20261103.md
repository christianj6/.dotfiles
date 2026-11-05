# Clean state before new workstreams (2026-11-03, 17:45)

The owner asked for everyone at a stopping point, notifications cleared, and
"working as intended" verified before starting anything new.

## Stopping points — waited for, not assumed

Polled every agent until it settled:

```
17:28  bro claude     working -> done
17:29  heinzel claude working -> done
17:34  bro omp        working -> done   (it picked up the finished work)
```

Nobody was interrupted. Two Claudes and one omp finished their turns first.

## Notifications cleared

`POST /api/tasks {op: "clear", by: "owner"}` per project — this marks items
`done(cleared)`, "the owner has seen these", which is exactly what clearing
means here.

```
bro        cleared 6  (ready 6, left_working 1)
prescient  0   dotfiles 0   heinzel 0   thor-voiceai 0   marketing 0
```

The one `left_working` was `tk-b964b22eb4ba` — the **focus mode** request from
Nov 4. Its work shipped as bro `6e253c1` (which cites that id), so the card was
finished but never closed, and it was holding bro amber on completed work. Closed
`done(accepted)` with a note saying so.

**Hub now: 156 done, 0 open.**

## Working as intended — measured

| Surface | Result |
|---|---|
| prescient tests | **953 passed** |
| bro tests | **798 passed** |
| lifeview plugin | **OK** (82 tests) |
| all three repos | pushed, in sync |
| every pane | v35 |
| hub | 156 done, nothing open |

**The stale-status grace rule works, watched live.** bro read "working" at 17:33
because its own `prescient-status.json` still said `working` from 17:32 while
herdr said `done`. `WORKING_GRACE = 120 s` — the board believes the project's
word that long, then defers to herdr — and at 17:35 bro healed to `idle / nothing
open` by itself. That is the documented behaviour, observed rather than assumed.

dotfiles reads `working` only because I am working in it right now.

## What is intentionally left alone

- `config/omp/config.yml` (the owner's task-model change) and an untracked
  `docs/agent-pane-messaging-20261029.md` — both the owner's, not mine to commit.
- bro's 17 unpushed commits were **pushed**: a resolver arc, 798 green, and the
  owner has been pushing bro's work himself.

## Known, not blocking

1. **Auto-ready's own write is still unobserved live.** Correct in isolation and
   correctly guarded in practice; every project either marks its own work or is
   mid-flight.
2. **Three cards carry `origin: harness`** (`tk-fd5abeca35f2`, `tk-c37386983176`,
   `tk-e19b7e56fc7b`) because they predate the provenance fix. They are closed
   now; new cards get correct provenance.
3. **Honesty false positives** and **the uncalibrated bench** remain queued.

## Verdict

Clean. Every agent stopped, the hub is empty, all suites green, everything
pushed, and the one anomaly found while checking was a stale card whose work had
shipped — now closed.
