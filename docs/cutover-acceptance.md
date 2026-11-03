# Cut-over acceptance record (2026-11-03)

The end-to-end loop is **proven**, not inferred. Verified by me directly in the hub store.

## First real hand-off (bro, dev)

| Item | Value |
|---|---|
| `tk-8076367bafcd` | `project=bro`, `target=dev`, `origin=owner`, `state=ready` |
| Path | `queued → working → ready`, driven by bro's own voice hand-off and the dev agent's own `start`/`ready` |

## Second hand-off (heinzel, dev) — the D1 regression case

| Item | Value |
|---|---|
| `tk-735885816f18` | `project=heinzel`, `target=dev`, `origin=owner`, `state=working` |
| Before the fix | the same replay produced `project=v2-w5p1a` (the pane name, not the repo) |

**Cause** (`cc1d35a`): a pane's project was derived from its herdr name; now it is the agent's repo — its cwd's toplevel basename, the board's rule. Verified by replaying `fix-heinzel.wav`.

## Data hygiene applied at acceptance

- Deleted the one bad row the pre-fix replay created (`tk-734c9ca38c19`, `project=v2-w5p1a`) — it duplicated `tk-735885816f18` with a wrong project. Deleting beat editing because the state machine has no "correct the project" op, and inventing one for a single bad row would be a worse trade.
- Deleted `tk-b9cb5adde0cd` (`project=hubdemo`, "wave 2 demo") — dry-run fixture residue.
- Verified **no stray origins** (all items are `bro`/`owner`/`harness`) and no dry-run rows remain.

Post-cleanup: 5 projects, no pane-named projects, `done=115 ready=2 working=1`.

## Honesty lint (the trust fix)

Verified by calling `honesty.unbacked()` directly:
- `"Got it — all notifications cleared…"` with only an inbox read → **`'clear'`** (flagged)
- same reply with a `clear:<project>` effect → `None` (passes)
- same reply after a **route** that went → still **`'clear'`** (correct: only a clear backs a clear claim)
- 24 eval cases in `testdata/eval/honesty-claims.json`, including the exact reply from the live run in both `backing: none` and `backing: clear` forms.

## State at hand-off to the owner

- Hub: 5 projects, `done=115 ready=2 working=1`; `/api/tasks` + `/api/tasks/status` + `/ranks` (v2).
- `bro serve` under the broker supervisor, `TASK_HUB=prescient`; **voice core intentionally down** (clean exit) — the coordinator brings it up on request for the next test.
- dotfiles: all panes v34, plugin on `TASK_HUB=prescient` with coordinators exempt from auto-task.
- All three repos pushed.

## Not done, deliberately

- Wave 5 storage removal (archive written and gitignored; bro's code still carries the local path behind `TASK_HUB=local`).
- Trello replication (outbox in place, replicator still a stub).
- The 25 historical duplicate-marker pairs on the board (invisible, left rather than guess which copy was edited).
