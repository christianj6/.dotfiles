# REPORT: one shared singleton lock for four plugins, locks and logs off /tmp, duplicates cleared

Spec: `docs/task-shared-singleton-lock.md`.

## Headline

- **One shared module:** `config/herdr/plugins/_shared/singleton.py`, with
  `SingletonLock`, `plugin_state_dir` and `acquire_or_exit`.
  - All four plugins import it: lifeview-fallback, claude-name, agent-discord and omp-watch.
  - None keeps its own lock code: no `LOCK_NB` remains in any of them.
- **Locks are off `/tmp`:** `~/.local/state/herdr/plugins/<plugin-id>/lock`.
- **Logs are off `/tmp`:**
  - lifeview: `…/dotfiles.lifeview-fallback/lifeview-fallback.log`
  - claude-name: `…/dotfiles.claude-name/claude-name-daemon.log`
  - omp-watch: `…/dotfiles.omp-watch/omp-watch-daemon.log`
  - agent-discord's `bridge.log` was already in `…/dotfiles.agent-discord/`.

  Log content format is unchanged.
- **One process each:** lifeview 1, claude-name 1, agent-discord 1, omp-watch 1.
  - The bot has **one** gateway connection and a real `bot ready` at 14:47:25.
- **Replaced-lock proof** for claude-name, agent-discord and omp-watch: the holder re-takes
  the path and the second instance exits 0. Output is pasted below.
- **No prescient task touched.**

## 1. The shared module

**Where it lives.** The plugins shared nothing before. Each is linked separately with
`herdr plugin link …/plugins/<name>`. The one precedent for cross-plugin code is lifeview
importing omp-watch through a `sys.path` insert of the sibling dir (`_omp_newest_session`).
I followed that pattern: each entry script does
`sys.path.insert(0, Path(__file__).resolve().parent.parent / "_shared")`, then
`from singleton import SingletonLock, plugin_state_dir`. Entry scripts are run as
`python3 <file>` from their plugin dir, by the toml hooks and by `workspace-up` alike, and
`.resolve()` follows the link to the real repo path.

**Behaviour.** One implementation, one behaviour. It is lifeview's `SingletonLock` from
`3a5f8c0`, moved, with a `log` callable added:

- the path is fixed per plugin id, never `/tmp`, and not `HERDR_PLUGIN_STATE_DIR`, which can
  differ by launcher;
- the parent directory is created on demand;
- `acquire()` checks `(st_dev, st_ino)` from `stat(path)` against `fstat(fd)`;
- `keep()` runs every tick. It re-takes a removed or replaced path, or returns False when
  another instance holds it.

**Where `keep()` is called in each plugin:**

| plugin | tick | on `keep()` False |
|---|---|---|
| lifeview-fallback | top of `run()` loop (10 s) | `run()` returns |
| claude-name | top of `run()` loop (5 s) | `run()` returns |
| omp-watch | top of `main()` tick, before the SIGHUP re-exec (3 s) | `sys.exit(0)`, which the crash loop re-raises |
| agent-discord | `orphan_watch` `tasks.loop` (10 s, started in `on_ready`) | `os._exit(0)`, the same exit the orphan check uses |

Each plugin's own exit-on-held behaviour is unchanged:

- lifeview and claude-name exit quietly;
- omp-watch prints its "another instance already holds" line;
- agent-discord logs "another bridge instance holds the lock -- exiting".

## 2. Logs off `/tmp`

- **lifeview:** `LOG_PATH` is now `…/dotfiles.lifeview-fallback/lifeview-fallback.log`. It is
  the target of `daemonize()`'s dup2.
- **claude-name:** `LOG_PATH` is now `…/dotfiles.claude-name/claude-name-daemon.log`, used the
  same way.
- **omp-watch:** `LOG_PATH = $OMP_WATCH_LOG or …/dotfiles.omp-watch/omp-watch-daemon.log`. It
  is only used with `--daemon`. The live instance runs under `[[startup]]` without
  `--daemon`, so its stdio is herdr's pipe, exactly as before.
- **agent-discord:** `bridge.log` was already `STATE_DIR/bridge.log`, outside `/tmp`. So
  **`workspace-up`'s `BRIDGE_LOG` did not need a change.** It still points at the right file,
  as the green discord health check shows. bot.py re-exports `LOG_FILE` from `common` so the
  shared consumer test can check it.
- **The old `/tmp` files are left alone,** not deleted or migrated, as instructed.
- **Outside the spec, one line, flagged:** `config/herdr/bin/workspace-rollout:102`. Its
  `WATCH_LOG` default pointed at `/tmp/omp-watch-daemon.log`, and the rollout tails that file
  for wedge detection. Left as it was, it would have read a log nobody writes any more. The
  default now points at the new omp-watch log; `$OMP_WATCH_LOG` still overrides it.
  `bash -n` passes.

**`/tmp` references left in the four plugins,** none of them a lock or a log:

- claude-name `MARKERS` (`/tmp/claude-config-versions`) and omp-watch's
  `/tmp/omp-config-versions`: inputs written by a Claude hook and an omp extension. Moving them
  means changing their writers.
- lifeview's `HUB_LAST_PATH` (`/tmp/lifeview-fallback.hub-last.json`): `--explain` state,
  which is also prune-vulnerable but harmless.
- comments.

## 3. Live duplicates cleared

**Before:**

- claude-name: 14514 (Nov 12, orphaned inode) and 47069 (Nov 18).
- agent-discord: 14457 (Nov 12) holding an unlinked `/tmp` lock.
- lifeview: 96401 (new lock, old in-file class).
- omp-watch: 14463 (`/tmp` lock).

**What I did:**

- **claude-name:** killed **both** 14514 and 47069. The spec said to keep the survivor, but
  47069 also ran the old code and held only the old `/tmp` lock, which the new code never
  looks at. So keeping it would have let a new-code daemon run beside it.
  - No event hook relaunched it within 60 s (no agent status change), so I started it the way
    the hook does: `cd claude-name && python3 names.py --daemon` → pid **20353**.
  - Neither daemon reads any hook-only environment: there is no `HERDR_PLUGIN_*` or
    `HERDR_PANE_ID` use in names.py or lifeview.py.
- **lifeview:** killed 96401 and started it the same way → pid **20359**.
- **omp-watch:** sent `kill -HUP 14463`. It re-execs itself with the new code, keeping the same
  pid. Python opens files close-on-exec, so the old `/tmp` lock was released, and the
  re-exec'd process holds `…/dotfiles.omp-watch/lock`.
- **agent-discord:** ran `python3 scripts/workspace-up --only discord-bot`. That is
  `workspace-up`'s own restart: bot.py was newer than the process, so it stopped it and started
  `bash run-bot.sh` with `HERDR_DISCORD_DETACHED=1`.

  ```
  discord-bot  running (pid 20900 ) up 0s   code 2m   old   ok: token ok, 24 channels resolve, Discord connects, bot ready   [restarted: code 7d newer than process (bot.py) -> started]
  ```

  - `bridge.log`: `[2026-11-19 14:47:25] bot ready as Herdr Integration#7459 …`
  - `pgrep -f 'agent-discord/bot\.py' | wc -l` → **1**.
  - Right after start it had two port-443 connections:
    - one to `162.159.137.232`, which is discord.com, the REST call made at startup; it closed
      within 20 s;
    - one to `162.159.130.234`, which is a `gateway.discord.gg` address.

    So there is **one gateway connection**, and it was still the only one after the
    replaced-lock test below.

**Counts after:** `pgrep -f` gives lifeview 1, claude-name 1, `agent-discord/bot\.py` 1,
`omp-watch/watch.py` 1. Each holds `~/.local/state/herdr/plugins/<id>/lock` (`lsof`).

## 4. Replaced-lock proof

**claude-name:**

```
$ holder=20353 ino=110215281
$ rm lock; : > lock
replaced ino=110216158 content=''
after tick: ino=110216158 content=20353
[claude-name] 14:48:06 lock path …/dotfiles.claude-name/lock was removed or replaced; re-took it
$ python3 names.py   # second instance, foreground
exit=0
$ python3 names.py --daemon; sleep 3
count=1 pids=20353
```

**agent-discord:**

```
$ holder=20900 ino=110215565
$ rm lock; : > lock
replaced ino=110216399 content=''
after tick: ino=110216399 content=20900
[2026-11-19 14:48:25] lock path …/dotfiles.agent-discord/lock was removed or replaced; re-took it
$ bash run-bot.sh   # second bot, foreground
exit=0
[2026-11-19 14:48:37] another bridge instance holds the lock -- exiting
count=1 pids=20900
  conn 192.168.0.152:51574->162.159.130.234:443      <- still exactly one gateway
```

**omp-watch:**

```
$ holder=14463
after tick: content=14463
$ python3 watch.py   # second instance
[omp-watch] another instance already holds …/dotfiles.omp-watch/lock -- exiting, not duplicating it
exit=0
count=1
```

lifeview was proven the same way in `docs/task-fix-duplicate-tasks.report.md`, with the same
class, now shared.

## Tests

| suite | result |
|---|---|
| `_shared/test_singleton.py` (new) | 11 tests OK |
| `lifeview-fallback/test_lifeview.py` | 141 OK |
| `claude-name/test_names.py` | exit 0 |
| `omp-watch/test_watch.py` | all 21 groups passed |
| `agent-discord/test_resolve.py` | 11 OK |
| `scripts/test_workspace_up.py` | 19 OK |

What the new shared tests cover:

- **Lock behaviour:**
  - a second instance on the same inode exits;
  - **a newcomer to a replaced path exits once the holder has re-taken it;**
  - a removed path is re-taken;
  - a newcomer that wins the race makes the old holder's `keep()` false;
  - a path replaced between open and flock is refused;
  - `acquire_or_exit` exits 0;
  - the state dir is not under `/tmp`.
- **One consumer test per plugin** (4 tests). Each loads the plugin's entry script and asserts:
  - its `SingletonLock` *is* the shared class;
  - its `LOCK_PATH` is under `~/.local/state/herdr/plugins/`;
  - its log path is not under `/tmp`;
  - its source has no `LOCK_NB`, so no private lock copy remains.

## `scripts/workspace-up`, full output (exit 1)

```
lifeview     running (pid 24415 ) up 1s   code 3m   old   ok: hub token found
discord-bot  running (pid 20900 ) up 1m   code 3m   old   ok: token ok, 24 channels resolve, Discord connects, bot ready
prescient    running (pid 68116 ) up 1h   code 1d   old   ok: /api/health answers 200
bro          running (pid 24490 ) up 0s   code 20h  old   ok: /health answers 200   [restarted: code 45m newer than process (voicebridge.py) -> started]
omp w5:p1R   topical          pid 49506  up 4d   ok: window 1000000, threshold 500000
omp w5:p1T   heinzel          pid 75495  up 4d   ok: window 1000000, threshold 500000
omp wD:p5    bro              pid 83146  up 21h  ok: window 1000000, threshold 500000
omp wD:p7    prescient        pid 452    up 21h  ok: window 1000000, threshold 500000
omp wD:p9    .dotfiles        pid 41690  up 20h  ok: window 1000000, threshold 500000
omp wG:p1    thor-voiceai     pid 84434  up 21h  ok: window 1000000, threshold 500000
omp wG:p6    ai-assisted-dev  pid 80155  up 7d   STALE: threshold 660000 vs config 500000
omp wG:pC    knowledge-graph  pid 4499   up 3d   ok: window 1000000, threshold 500000
omp wG:pE    market-research  pid 37479  up 3d   ok: window 1000000, threshold 500000
omp wG:pG    telia-sms-fraud  pid 14852  up 2d   ok: window 1000000, threshold 500000
workspace: 4 running, 0 started, 0 stale, 1 restarted, 0 unhealthy, 1 omp stale, 1 need you - omp wG:p6 (ai-assisted-dev): threshold 660000 vs config 500000 - restart its omp (/exit, then ctrl+a in the pane)
  omp wG:p6 (ai-assisted-dev): threshold 660000 vs config 500000 - restart its omp (/exit, then ctrl+a in the pane)
```

Notes on this output:

- **`bro … restarted`:** this run restarted bro's server (`bro serve`) on its own, because bro's
  code (`voicebridge.py`, in the bro repo) was 45 min newer than the process. That is
  `workspace-up` doing its normal job, a side effect of running it as asked. It came back
  healthy.
- **`lifeview … pid 24415 up 1s`:** this was a launch from herdr's event hook, caught in the
  instant before it exited on the lock. `workspace-up` reports the newest process matching
  `lifeview\.py --daemon`. The real daemon is still 20359, holding the lock, and a moment later
  `pgrep` shows only 20359. This reporting quirk is not a second daemon, and I left
  `workspace-up` alone; it could prefer the lock holder's pid, a possible follow-up.
- **`wG:p6`:** named and left alone, as instructed.

## Changed files

- `config/herdr/plugins/_shared/singleton.py`, `_shared/test_singleton.py`: new.
- `config/herdr/plugins/lifeview-fallback/lifeview.py`: the class is now imported, and
  `LOG_PATH` moved.
- `config/herdr/plugins/claude-name/names.py`: shared lock, `keep()` in `run()`, `LOG_PATH`
  moved, unused `fcntl` import dropped.
- `config/herdr/plugins/omp-watch/watch.py`: shared lock, `keep()` in the tick, `LOG_PATH`
  constant moved, unused `fcntl` import dropped.
- `config/herdr/plugins/agent-discord/bot.py`: shared lock, `keep()` in `orphan_watch`,
  `LOG_FILE` re-exported, unused `fcntl` import dropped.
- `config/herdr/bin/workspace-rollout`: the one-line `WATCH_LOG` default, outside the spec and
  flagged above.
- `config/claude/settings.json`: still an uncommitted change I did not make; not in the
  commit.
