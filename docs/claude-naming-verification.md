# Claude pane naming verification

Run 2026-11-02 on herdr 0.9.5 and Claude Code 2.1.316, in a throwaway workspace
that was closed afterwards. Times are local. Lines tagged `[claude-name]` come
from `/tmp/claude-name-daemon.log`.

## Result

| Check | Result |
| --- | --- |
| New pane named without a hand rename, within ~10s | Pass: 4s with the plugin running |
| No rename while `working` | Pass, after one invalid first attempt |
| Second tick leaves names alone | Pass |
| Recovers after being killed | Pass: 6s, through the event hook |
| Starts after a server restart | Not tested |

The suffix is `pane_id.replace(":", "").lower()`, copied from omp-watch, so
`wD:pA` gives `wdpa`. The spec's example `wdpA` is not what that code produces.

## Existing panes

Before:

    wD:p9 omp-v25-wdp9 omp working
    wD:pA claude-dotfiles-2 claude working
    wD:p6 None claude idle
    w5:p1A None claude idle

After the plugin's first tick:

    [claude-name] 07:58:27 wD:p6: None -> 'claude-v2-wdp6'
    [claude-name] 07:58:27 w5:p1A: None -> 'claude-v2-w5p1a'

    wD:p9 omp-v25-wdp9 omp working
    wD:pA claude-dotfiles-2 claude working
    wD:p6 claude-v2-wdp6 claude idle
    w5:p1A claude-v2-w5p1a claude idle

`wD:pA` was mid-turn throughout, so it kept its old name. It is the pane that
ran this verification.

## New pane

    before (07:58:58)
    wH:p1 claude-v2-whp1 claude done
    after (07:59:02) +4s
    wH:p1 claude-v2-whp1 claude done
    wH:p2 claude-v2-whp2 claude unknown
    [claude-name] 07:59:02 wH:p2: None -> 'claude-v2-whp2'

## No rename while working

The pane ran a blocking foreground command, was renamed by hand mid-turn, and
was watched until the turn ended:

    08:00:03 wH:p1 hand-name claude working
    08:00:10 wH:p1 hand-name claude working
    08:00:16 wH:p1 hand-name claude working
    08:00:22 wH:p1 hand-name claude working
    08:00:28 wH:p1 hand-name claude working
    08:00:34 wH:p1 hand-name claude working
    [claude-name] 08:00:38 wH:p1: 'hand-name' -> 'claude-v2-whp1'
    08:00:40 wH:p1 claude-v2-whp1 claude done

The first attempt proved nothing. Claude refuses a foreground `sleep`, moved it
to the background and ended its turn, so that rename landed on a `done` pane.

## Idempotence

Over 16 seconds, about three ticks:

    log lines added: 0
    revisions before {'wH:p1': 2, 'wH:p2': 1}
    revisions after  {'wH:p1': 2, 'wH:p2': 1}

## Supervision

`names.py` has two launchers, both `python3 names.py --daemon`:

- `[[startup]]` fires at server start and does not supervise anything.
- `[[events]]` on `pane.agent_status_changed` fires on any agent's status
  change. The singleton lock makes that a no-op while an instance runs.

So herdr does not supervise the process. The event hook relaunches it.

    === kill 08:02:15
    52925     1 python3 names.py --daemon
    kill -9 52925 rc=0
    === 08:02:22 +6s name=[claude-v2-whp3] without any prompt
    59188     1 python3 names.py --daemon
    [claude-name] 08:02:21 wH:p3: None -> 'claude-v2-whp3'

`herdr plugin link` also picked up the hook without a server restart, but it
did not start the plugin. The first launch came about 80 seconds later, on the
next status change.

**Limit:** recovery needs a status change on some pane. With every agent steady,
a dead plugin stays dead, and a pane that only reaches `unknown` does not fire
the event. Manual start:

    python3 ~/.dotfiles/config/herdr/plugins/claude-name/names.py --daemon

## Not tested

- The `[[startup]]` hook. Testing it means restarting the server, which would
  disturb every live pane.
- The daemon's exit when the server dies, for the same reason.
- `claude --version` failing, live. The fallback name is covered by
  `test_names.py` only.
