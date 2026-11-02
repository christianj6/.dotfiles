# Life-view fallback verification

Run 2026-11-02 on herdr 0.9.5, in throwaway workspaces that were closed
afterwards. Times are local. Lines tagged `[lifeview-fallback]` come from
`/tmp/lifeview-fallback.log`. Plugin: `config/herdr/plugins/lifeview-fallback/`.

This covers the plugin's first version. Its entries are now marked
`"by": "harness"` / `harness: ...` (old `fallback` entries migrate on the next
tick), and it also auto-marks bro tasks ready: see `docs/lifeview-automation.md`.

## Result

| Check | Result |
| --- | --- |
| New claude pane with no entry gets a fallback within ~15 s | Pass: 10 s |
| The dashboard (`agent_board._agents`) resolves it | Pass; the extra `"by"` key is ignored |
| Fallback follows herdr (idle → working) | Pass |
| The agent's own `prescient status` replaces the fallback | Pass, in place (same pane-id key) |
| A fresh agent-authored entry is not overwritten | Pass: a contradicted `working` kept 185 s, replaced on the first tick past 180 s |
| Settled agent entries in live repos untouched | Pass: before/after diff shows only agent writes and one fallback |
| Fallback removed when its pane closes | Pass |
| Relaunched after being killed | Pass: 6 s after the next status change |
| Unit tests (`python3 test_lifeview.py`) | 11 pass |

## How it decides

- Keyed by pane id, as `prescient status` keys entries, so the agent's next
  write replaces the fallback in place. A fallback carries `"by": "fallback"`
  and a `fallback: ...` line.
- herdr `working` → `working` (`ttl_s` 300, refreshed while herdr agrees);
  `idle`/`done` → `idle`; `blocked` → `blocked`. herdr `unknown` or no status
  says nothing, so nothing is written.
- An agent-authored entry is never touched while younger than 180 s or
  within its own `ttl_s`. Past that, only a `working` that herdr no longer
  corroborates is replaced. Agent `idle`/`standby`/`blocked` entries stand
  until the agent replaces them (see "Deviation" below).
- A fallback is dropped when the agent has its own entry under its herdr
  name, or when its pane is gone.
- Writes take prescient's `.prescient-status.json.lock` and re-decide under
  it, then replace the file whole, like `write_status()`.
- Only repos whose git toplevel already ignores `prescient-status.json` and
  its lock are written to. On this box: .dotfiles, prescient, bro, heinzel.

### Deviation from the spec

The spec calls an entry stale when "older than the grace". The live repos
showed why that can't apply to settled states: several omp coordinators had
their own `idle` entries while herdr reported them `working`, which prescient's
docs say can stick for hours ("nineteen hours, standing by"). Replacing those
would make the icon worse. So only the spec's second staleness test is used,
"a `working` that herdr no longer corroborates", and it matches how prescient
reads the file.

## New pane: fallback appears

Scratch claude in a fresh tab (`cd ~/.dotfiles && claude`), no prompt given:

    claude started in wJ:p3 09:36:47
    +4s  herdr=[('claude-v2-wjp3', 'idle')] file=None
    +8s  herdr=[('claude-v2-wjp3', 'idle')] file=None
    +10s herdr=[('claude-v2-wjp3', 'idle')] file={'state': 'idle', 'at': '2026-11-02T09:36:57+01:00', 'line': 'fallback: herdr idle', 'by': 'fallback'}
    [lifeview-fallback] 09:36:57 /Users/christianjohnson/.dotfiles: wJ:p3 -> idle (fallback: herdr idle)

## Dashboard resolves it

    .venv/bin/python -c 'from prescient.gantt import agent_board; ...agent_board._agents({})'
    {'name': 'claude-v2-wjp3', 'project': 'dotfiles', 'kind': 'claude', 'status': 'idle', 'title': 'Claude Code',
     'said': {'state': 'idle', 'line': 'fallback: herdr idle', 'at': '2026-11-02T09:36:57+01:00'}}
    {'name': 'claude-v2-wdpc', 'project': 'prescient', 'kind': 'claude', 'status': 'idle', 'title': '...',
     'said': {'state': 'idle', 'line': 'fallback: herdr idle', 'at': '2026-11-02T09:34:54+01:00'}}

`_own_status()` copies only state/line/at, so `"by"` never reaches the page.
The card shows the `fallback: ...` line.

## Agent writes its own word

The scratch agent was prompted to run
`prescient status idle "scratch agent: own word"`:

    prompted 09:37:35
    +3s  herdr=['working'] file={'state': 'idle', ..., 'by': 'fallback'}
    +6s  herdr=['working'] file={'state': 'working', 'at': '09:37:38', 'line': 'fallback: herdr reports working', 'by': 'fallback', 'ttl_s': 300.0}
    +15s herdr=['working'] file={'state': 'idle', 'at': '2026-11-02T09:37:49+01:00', 'line': 'scratch agent: own word'}
    +18s herdr=['done']    file={'state': 'idle', 'at': '2026-11-02T09:37:49+01:00', 'line': 'scratch agent: own word'}
    ... unchanged through +61s

The agent's entry replaced the fallback, and was not overwritten even while
herdr still said `working` (+15 s).

## Fresh agent entry not overwritten

An agent-authored `working` written through prescient's own `write_status()`
while herdr said `done`, which is the strongest contradiction:

    {'state': 'working', 'at': '2026-11-02T09:38:49+01:00', 'line': 'agent-authored working, herdr says done'}
    +15s ... +180s herdr=['done'] file={'state': 'working', ..., 'line': 'agent-authored working, herdr says done'}
    +195s herdr=['done'] file={'state': 'idle', 'at': '2026-11-02T09:41:54+01:00', 'line': 'fallback: herdr idle', 'by': 'fallback'}
    [lifeview-fallback] 09:41:54 /Users/christianjohnson/.dotfiles: wJ:p3 -> idle (fallback: herdr idle)

## Live repos untouched

Before/after diff of all four status files across the run (agent-authored
entries only change when their agents write):

- .dotfiles: no change. This pane's own `working` entry (stale, but herdr
  agrees) stood.
- prescient: `wD:p7` added by that agent itself; `wD:pC` (a claude pane with
  no entry) gained `fallback: herdr idle`.
- bro: `wD:p6` updated by that agent itself (no `by`, not in the log).
- heinzel: no change.

Full plugin log for the run:

    09:34:54 .../prescient: wD:pC -> idle (fallback: herdr idle)
    09:36:57 .../.dotfiles: wJ:p3 -> idle (fallback: herdr idle)
    09:37:38 .../.dotfiles: wJ:p3 -> working (fallback: herdr reports working)
    09:41:54 .../.dotfiles: wJ:p3 -> idle (fallback: herdr idle)
    09:42:35 .../.dotfiles: wJ:p3 fallback removed      <- workspace closed 09:42:29
    09:45:22 .../.dotfiles: wK:p1 -> idle (fallback: herdr idle)
    09:45:42 .../.dotfiles: wK:p1 fallback removed

## Supervision

Same shape as claude-name: `[[startup]]` at server start, and `[[events]]` on
`pane.agent_status_changed`. Both launch `lifeview.py --daemon`, and the
singleton lock (`/tmp/lifeview-fallback.lock`) makes repeat launches a no-op.

    killed 43246 09:43:05
    not relaunched within 120s          <- no agent changed status meanwhile
    status-change trigger: claude in wK:p1 09:45:17
    relaunched pid=62290 09:45:23

**Limit:** as with claude-name, recovery needs some pane's status to change.
`herdr plugin link` does not start it. Manual start:

    python3 ~/.dotfiles/config/herdr/plugins/lifeview-fallback/lifeview.py --daemon

`--once` runs a single tick in the foreground.

## Not tested

- The `[[startup]]` hook and exit-on-server-death (would need a server
  restart, disturbing every live pane).
- A herdr `blocked` pane live. The mapping is covered by unit tests only.
- An agent keyed by its herdr name (`--as`) rather than pane id, live. The
  drop rule is covered by unit tests only.

## Gotcha found on the way

A workspace created with `--cwd ~/.dotfiles` opens nvim in its root pane, and
so does a split from it. `pane run ... claude` then pastes into nvim. Use
`herdr tab create` (a clean `$HOME` shell) and `pane run <p> "cd <dir> && claude"`.
