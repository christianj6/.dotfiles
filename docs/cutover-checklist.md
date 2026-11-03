# Cut-over checklist (task hub)

Verified pieces, in the order they must flip. **Nothing flips until every box above the line is ticked.**

## Pre-cut-over (all verified)
- [x] prescient hub: store + machine + HTTP + CLI + import — `fc9f17b`, `a2dab97`, 779 tests
- [x] Real import: 99 items, bro's `tasks.json` byte-identical (`b04a6ea2…`)
- [x] Quarantine decisioned: none resurrected; archive-before-delete for wave 5 (`adebfed`)
- [x] bro client: `hub.py`, `Destination.role`, project chain — `0fa1500`, `89cf31e`
- [x] bro call-site switch behind `TASK_HUB` (default `local`) — `f629864`, 488 tests
- [x] bro Q1/Q2: plan+tweak → `(prescient, dev)`; refiles create linked items — `993358a`, 497 tests
- [x] dotfiles plugin: `LIFEVIEW_TASK_HUB` (default `bro`) + hub create/list/ready — `abdeacd`, 49 tests
- [x] dotfiles instructions: verbs → `prescient task …`, VERSION 34 — `d549835`
- [x] Live state-machine leg verified by me: created→queued→working→ready→done, illegal refused;
      failed-nudge case honest (`nudged: failed (retryable)`, "no coordinator runs in <project>")

## Gate
- [ ] **bro tray proxy**: `server.py` `/api/tasks*` routed through `taskhub` (spec sent). Without it,
      `TASK_HUB=prescient` leaves the tray writing a store that refuses writes. **Must land first.**

## The flip (one session, in this order)
1. [ ] bro: `TASK_HUB=prescient` becomes the default; `bro task …` → HTTP forwarder with deprecation line
2. [ ] dotfiles: panes rolled to VERSION 34 (instructions take effect)
3. [ ] dotfiles: `LIFEVIEW_TASK_HUB=prescient` in the plugin's environment/config
4. [ ] prescient: wave 4 — `{status, why}` + ranks published (plugin may then drop its tables)

## Verification after the flip
- [ ] A real voice hand-off creates a hub item and nudges the coordinator (`nudged: ok` on the nested path)
- [ ] The coordinator `prescient task start`s it; an agent `ready`s it; the icon goes amber → green
- [ ] `prescient task list` and the tray show the same items (one store)
- [ ] A hub-down scenario fails closed with the hub line — never local data (A19)
- [ ] No writes to `data/tasks.json` (mtime/hash unchanged) for a day

## Rollback
Set `TASK_HUB=local` in bro and `LIFEVIEW_TASK_HUB=bro` in dotfiles, restart both. The hub DB keeps
everything written meanwhile; `data/tasks.json` is still intact until wave 5, so local resumes where it left off.
That is the reason the store is archived before deletion, not after.
