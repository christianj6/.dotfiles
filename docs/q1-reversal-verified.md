# Q1 reversal: verified end to end (2026-11-03)

Reversal landed in bro `8828233` (529 tests). I verified it myself, on the real stack — not from the report.

## The rule, confirmed in code

`bro/taskhub.py:155` — `HUB_ROLES = ("coordinator", "dev")`, with `queue` explicitly excluded and the reversal named in the comment.

## Real prescient destinations (not a hardcoded list)

```
plan                 role='queue'        on_hub=False   hub_target raises NotATask: plan (queue) is not a hub task
tweak                role='queue'        on_hub=False   hub_target raises NotATask: tweak (queue) is not a hub task
coordinator:heinzel  role='coordinator'  on_hub=True    hub_target -> ('heinzel', 'coordinator')
top                  role='dev'          on_hub=True    hub_target -> ('bro', 'dev')
```

Both queue destinations derive their role from the real `Destination`, so the invariant test's shell-out to prescient's venv is checking a true fact.

## The live write — the proof the coordinator could not give

Its plan replays ran without `--live`, so they were dry runs and wrote nothing anywhere. It said so itself rather than claiming a write. I ran the real path instead:

**Plan** — real `PrescientStack.deliver('plan', card)`, inbox redirected to a temp file:
```
Receipt(ok=True, text="It's in your planning inbox, place it from there when you're ready.", ref='ib-ffd66fd4300b')
inbox items: ['Good biodeed milk']      hub rows: 118 -> 118
```
An `ib-` ref (a capture), the inbox gained the item, **no hub row**. That is the live proof.

**Coordinator** — `taskhub.create(coordinator:heinzel, ...)` under `TASK_HUB=prescient`:
```
hub create -> tk-f06d34f02555 heinzel coordinator
hub rows: 118 -> 119 | inbox: 0 -> 0
```
Hub item created, **inbox untouched**. Both directions now proven under live semantics, not just unit tests.

Also confirmed for free: under `TASK_HUB=local`, `taskhub.create` raises `RuntimeError("a hub call under TASK_HUB=local")`. It fails closed instead of silently writing the wrong store — the contract we specified.

## Data repaired

- `tk-0c432af1f87b` ("Good biodeed milk in my planning inbox") — removed from the hub and **restored as an inbox capture** (`ib-a4ea2a45a052`), recovered before deletion rather than just deleted. That was the whole point of the bug.
- `tk-734c9ca38c19` (`v2-w5p1a`) — already removed in the earlier pass.
- `tk-b1ef17e7ba16` — **I deleted this by mistake.** It was a real owner task ("Put this in Heinzel's inbox, the boss fight needs a second phase"), not my probe. Restored as `tk-59201a566bd2` (`heinzel/coordinator`, queued, origin owner). The content and target are exact; the id and the two original events are not recoverable, so its history starts over. Worth noting the failure mode: I grouped a cleanup `DELETE ... IN (...)` with my own probe id in one statement, and the id I "recognised" as disposable was real.

## Final state

```
done=115  queued=1  ready=2
tk-8076367bafcd  bro/dev          ready     (first real voice hand-off)
tk-735885816f18  heinzel/dev      ready     (D1 fix, correctly filed)
tk-59201a566bd2  heinzel/coord    queued    (restored)
```
Inbox: one capture. Projects: bro 33, prescient 26, heinzel 21, dotfiles 20, thor-voiceai 17. No stray origins.
