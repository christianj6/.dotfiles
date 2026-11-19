# REPORT: workspace-up judges the lock holder, not a hook launch in flight

Spec: `docs/task-workspace-up-lockholder.md`.

## Headline

- **New `serving(procs, lock)` in `scripts/workspace-up`,** unit-testable on its own. It picks
  the process to judge:
  - the **lock holder** when the piece's lock file names a live matching pid;
  - otherwise the newest match, and it says why;
  - the newest match for unlocked pieces (prescient, bro), exactly as before.
- **Same treatment for every locked piece,** through a new `Piece.lock` field. There is no
  lifeview special case: lifeview, discord-bot, **omp-watch** and **claude-name** all use it.
  The last two were not `workspace-up` pieces at all; see "Scope note".
- **The in-flight launch is named on the line:**
  `running (pid 62423 lock holder; 63275 launch in flight)`.
- **What counts as stale is unchanged** (code mtime against process start). Only *which*
  process is judged changed.
- **Restart still stops every match,** in-flight launches included, then starts one.

## Reproduce, then fix

**Before the fix.** The serving daemon was 54547; I touched `lifeview.py` so the code was
newer than it, and put a stand-in launch in flight:

```
lock holder: 54547  matches: 54547 59778
$ python3 scripts/workspace-up --only lifeview   # BEFORE the fix
lifeview     running (pid 59775 ) up 1s   code 1s   old   ok: hub token found
workspace: 1 running, 0 started, 0 stale, 0 restarted, 0 unhealthy, 0 need you
lock holder after: 54547 started Thu Nov 19 15:02:19 2026          <- stale daemon untouched
```

**After the fix,** using `repro.sh`, the same setup in a script file (see "A trap I hit"):

```
before: holder 62423 (started 15:05:48), all matches: 62423 63275
$ python3 scripts/workspace-up --dry-run --only lifeview
lifeview     running (pid 62423 lock holder; 63275 launch in flight) up 28s  code 1s   old   ok: hub token found   [would restart: code 27s newer than process (lifeview.py)]
workspace: 1 running, 0 started, 1 stale, 0 restarted, 0 unhealthy, 0 need you
after: holder 62423 ..., all matches: 62423 63275                  <- dry run touched nothing
======
before: holder 62423 (started 15:05:48), all matches: 62423 63275 63380
$ python3 scripts/workspace-up --only lifeview
lifeview     running (pid 63514 ) up 0s   code 1s   old   ok: hub token found   [restarted: code 31s newer than process (lifeview.py) -> started]
workspace: 1 running, 0 started, 0 stale, 1 restarted, 0 unhealthy, 0 need you
after: holder 63514 (started 15:06:22), all matches: 63514         <- holder and launches stopped, one daemon
```

**Dead pid in the lock** (acceptance 3). I wrote 99999 into the live lock file in place, so
the inode and the holder's flock were unaffected, ran a dry run, then restored the real pid:

```
lifeview     running (pid 63514 lock names pid 99999, which is not running; judged the newest match) up 2m ... ok
restored lock=63514 inode unchanged: yes
```

## Healthy: no thrash (acceptance 2), and the services unchanged (acceptance 4)

**Run 1:** the only action was a one-time omp-watch restart. Its process dated from Nov 12,
because the `HUP` reload I did earlier re-execs in place and keeps the original start time.

```
omp-watch    running (pid 68815 ) up 0s   code 24m  old   ok:    [restarted: code 7d newer than process (watch.py) -> started]
workspace: 6 running, 0 started, 0 stale, 1 restarted, 0 unhealthy, 1 omp stale, 1 need you - omp wG:p6 ...
```

**Run 2:** nothing to do.

```
lifeview     running (pid 63514 ) up 2m   code 2m   old   ok: hub token found
discord-bot  running (pid 20900 ) up 21m  code 24m  old   ok: token ok, 24 channels resolve, Discord connects, bot ready
omp-watch    running (pid 68815 ) up 5s   code 24m  old   ok:
claude-name  running (pid 20353 ) up 22m  code 24m  old   ok:
prescient    running (pid 68116 ) up 2h   code 1d   old   ok: /api/health answers 200
bro          running (pid 24490 ) up 20m  code 20h  old   ok: /health answers 200
workspace: 6 running, 0 started, 0 stale, 0 restarted, 0 unhealthy, 1 omp stale, 1 need you - omp wG:p6 (ai-assisted-dev): ...
```

- **Daemon counts:** lifeview 1, claude-name 1, agent-discord 1, omp-watch 1.
- **The restarted omp-watch (68815)** holds `…/dotfiles.omp-watch/lock`, has ppid 1
  (daemonized), and omp agent states are still being reported.
- **omp-watch's interpreter changed.** It now runs on the Python `workspace-up` runs on, not
  herdr's miniconda `python3`. `watch.py`'s tests pass on it.
- **`wG:p6`** is still named and left alone.

## Scope note: omp-watch and claude-name are now `workspace-up` pieces

The spec lists them among the locked pieces, but `PIECES` only had lifeview, discord-bot,
prescient and bro. I added both, with the same shape as the others:

- the lock at `~/.local/state/herdr/plugins/dotfiles.<id>/lock`;
- `code()` covering their entry script **and** `_shared/singleton.py`;
- launched with `--daemon` **by absolute path**, so the started process matches the same regex
  as herdr's own launch (`…/omp-watch/watch.py`).

So `workspace-up` now restarts them when their code changes, closing the gap I filled by hand
with a `HUP` last round. Their health check is the default (process present).

`_shared/singleton.py` is now part of the code of lifeview and discord-bot too, so a change to
the shared lock restarts every consumer.

## Tests (`scripts/test_workspace_up.py`, 27 tests, all passing)

**`Serving`** (pure, no live daemon):

- the lock holder is judged over a newer launch, with the note
  `lock holder; 200 launch in flight`;
- a lock holder alone gets no note;
- a dead pid in the lock falls back to the newest match;
- a missing, empty or garbage lock falls back;
- an unlocked piece judges the newest match, as before;
- every plugin-daemon piece has its lock and the shared module in its code, and
  prescient and bro have none.

**`ServingLive`** (fake sleeper processes plus a temp lock):

- a stale holder behind a fresh launch: the dry run names both pids and says `would restart`,
  then the real run restarts and leaves one new process;
- a fresh holder with a launch in flight is left alone (`0 stale, 0 restarted`).

The existing tests stay green.

## A trap I hit (an existing hazard, not changed)

Pieces are matched by a regex over `ps` command lines, and a restart stops **every** match. My
first two "after" attempts put the string `lifeview.py --daemon` in my own shell command, once
in a stand-in's arguments and once in a `printf`. `workspace-up` matched my shell, stopped it
(exit 144), and lost the output. The restart itself happened both times: 54547 → 61753.

Anyone testing `workspace-up` by hand should keep piece patterns out of their command line.
Hence `repro.sh`. A stricter match (for example, only processes whose argv[0] is a Python) is
possible, but outside this spec.

## Changed files

- `scripts/workspace-up`: `Piece.lock`, `PLUGIN_STATE`, `SHARED`, `lock_pid()` and `serving()`;
  `run()` judges and prints `serving()`'s choice; the lifeview and discord-bot pieces get a lock
  and the shared code; new omp-watch and claude-name pieces.
- `scripts/test_workspace_up.py`: `Serving` and `ServingLive`.
- `config/claude/settings.json`: still an uncommitted change I did not make; not in the commit.
