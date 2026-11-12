# Autorestore: verified (2026-11-12)

Owner's goal: *"after restart i wanna just be able to type herdr and then have prescient etc up
and running the way i like … the goal is to reduce churn after system restarts."*

## What now happens at herdr start

`config/herdr/plugins/workspace-restore/` — a `[[startup]]`-only plugin, enabled:

```
dotfiles.workspace-restore (workspace restore) enabled
```

It runs `scripts/workspace-up` (the services), then restores the pane shape. **Startup only, by
design**: no event hook, no keybinding, no `config.toml` change — so nothing can get in the way
of opening a pane or using a terminal afterwards.

## The state it produces, verified

```
$ scripts/herdr-restore
wD:p9   omp     ok
wD:pJ   claude  ok            <- dotfiles: nvim+omp left, claude right
wD:p7   omp     ok
wD:pC   claude  ok            <- prescient
wD:p5   omp     ok
wD:p6   claude  ok            <- bro
w5:p1D  omp     ok
w5:p1A  claude  ok            <- heinzel
wG:p1   omp     ok
wG:t1   claude  work project: no claude pane, by owner rule
```

**Idempotent**: a second real run produced identical output and changed nothing.

## The two decisions that make it safe

**Work projects never get a claude pane** — `WORK_MARKER = "Desktop/tallence"` in the plugin, and
it holds even with `--create-missing`. thor reports `work project: no claude pane, by owner
rule` rather than a missing pane. That is the owner's rule from today, and it is why the pane he
closed will not be rebuilt on every boot.

**A missing pane is never created automatically.** From the plugin's own docstring: *"a pane that
does not exist is never created. herdr restores the layout the owner left, so a missing right
pane means he closed it; only an existing-but-empty pane is filled."* That is the correct
reading of "do not override config that stops me using herdr normally" — the restore fills
what the reboot emptied, and leaves what the owner deliberately closed alone.

## Verified per state

| pane state | action |
|---|---|
| nvim without a terminal | `ctrl+a` to open the omp REPL |
| idle shell | run nvim, then `ctrl+a` |
| right pane has an agent | ok |
| right pane idle shell | `herdr agent start claude` |
| right pane idle nvim | split with `HERDR_NO_NVIM=1`, start claude, close the nvim — **idle only** (no unsaved buffer, no terminal) |
| right pane has unsaved work | left alone |
| right pane absent | left alone unless `--create-missing` |

## Not yet proven

**The hook has not fired from a real server start.** Everything above was run by hand. The
registration is confirmed (`plugin list` shows it enabled), the command is confirmed, and the
script is confirmed — but "herdr start → everything up" is only *observed* after the next actual
restart. That is the one check this verification cannot make.

Also unproven: `workspace-up` running from inside the startup hook. It works when invoked by
hand (`2 started` this morning), but the hook's environment differs — `HERDR_PLUGIN_STATE_DIR`,
a detached process, and no interactive shell. The restore log at
`$HERDR_PLUGIN_STATE_DIR/restore.log` is where the first real run will say what it did.

## What I would check after the next reboot

1. `herdr` alone → are prescient (8765) and bro (8766) answering?
2. `scripts/herdr-restore --dry-run` → should be all `ok`, no changes needed.
3. `cat $HERDR_PLUGIN_STATE_DIR/restore.log` → did the hook run, and what did it say?
