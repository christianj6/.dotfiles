# TASK: the /tmp lock fault is live in three more plugins — extract the fix, apply it everywhere

Follow-on to `docs/task-fix-duplicate-tasks.md` (fixed, commit `3a5f8c0`). Your report's
"Outside the spec" section found the same fault elsewhere and correctly stopped. This
spec is the scope to fix it.

## The class

`fcntl.flock` on a **path under `/tmp`** is not mutual exclusion: macOS unlinks `/tmp`
entries, which frees the pathname but leaves a live process holding the orphaned inode.
The next launch creates a fresh file, flocks it successfully, and both processes believe
they are the singleton. Your `SingletonLock` (path outside `/tmp` + `(st_dev, st_ino)`
verify after acquire + `keep()` re-take each tick) is the fix. Three more plugins need it.

## Live state, verified by the coordinator

| plugin | state | consequence |
|---|---|---|
| **agent-discord** | `/tmp/herdr-agent-discord.lock` **does not exist**; bot pid 14457 holds orphaned inode 92236290 | **the next launch starts a second bot** — duplicate Discord messages |
| **claude-name** | 2 daemons: 14514 (Nov 12, orphaned inode 92236287) and 47069 (Nov 18, inode 108131616) | duplicate pane renames / races |
| **omp-watch** | 1 process, path still names its inode | latent — same weakness |

## What to do

### 1. Extract `SingletonLock` into one shared module

It currently lives inside `config/herdr/plugins/lifeview-fallback/lifeview.py`. Move it to a
single importable module (e.g. `config/herdr/plugins/_shared/singleton.py`, or wherever the
plugins can import from without duplicating code — check how the other plugins already share
anything before inventing a location) and have **all four** plugins import it:

- `lifeview-fallback`, `claude-name`, `agent-discord`, `omp-watch`.

Hard requirements for the shared version:

- **the lock path is never under `/tmp`** — default to
  `~/.local/state/herdr/plugins/<plugin-id>/lock`, created on demand;
- **inode verify after acquire** (`stat(path)` vs `fstat(fd)` on `(st_dev, st_ino)`);
- **`keep()` each tick**, re-taking the path or exiting if another instance holds it;
- a unit test proving the replaced-path newcomer exits, shared by all four consumers.

Do not change lock semantics per plugin; one implementation, one behaviour.

### 2. Move the logs off `/tmp` too

`LOG_PATH` is still `/tmp/lifeview-fallback.log`, and this actively hid the bug: the older
daemon's log went to an orphaned inode, so **its copies of the duplicate opens never appeared
in the file the coordinator read**. A diagnostic log that silently disappears is worse than none.

- Move each plugin's log to `~/.local/state/herdr/plugins/<plugin-id>/` (next to its lock).
- Keep the log **content format** identical — people and `workspace-up` grep it
  (`workspace-up` reads the bridge log for discord readiness, so update that path).
- Leave the old `/tmp` files alone; do not delete or migrate them.

### 3. Clear the live duplicates

- **agent-discord:** exactly one bot after the change. The current bot (14457) holds an
  orphaned lock inode, so the fixed code cannot simply re-use it — restart it **the same way
  `workspace-up` does**, then confirm `pgrep -f "agent-discord/bot.py" | wc -l` → **1** and
  that its log records a live gateway connection (`bot ready`), not just a process. A second
  bot must not be running: check for more than one gateway connection.
- **claude-name:** exactly one daemon; kill the older (14514, orphaned inode), confirm the
  survivor runs the new code.
- **omp-watch:** it is healthy, but move it to the shared lock so it cannot regress.

### 4. Reproduce the fault, then prove the fix, for each plugin

Same test you used for lifeview: replace the lock file while the daemon runs, start a second
instance, show it **exits**. Do it for at least `claude-name` and `agent-discord` — those had
the live duplicates. Paste the commands and the observed output in the report.

## Acceptance

1. One shared singleton module; all four plugins import it; no plugin keeps its own copy.
2. No plugin lock or log path under `/tmp` (`grep -rn '/tmp' config/herdr/plugins/` shows only
   comments/none for these four).
3. `pgrep` counts: lifeview **1**, claude-name **1**, agent-discord **1**, omp-watch **1**.
4. agent-discord has **one** gateway connection and logs a real `bot ready`; `workspace-up`'s
   discord health check still works (it reads the log path you moved — update it).
5. The replaced-lock test passes for claude-name and agent-discord, output pasted.
6. All existing plugin tests green; the shared module has its own tests.
7. Re-run `scripts/workspace-up` and paste its full output.

## Rules

- **Scope is these four plugins plus the shared module and `workspace-up`'s log path.** Nothing else.
- If a plugin's launch path cannot use the shared module without a restructure you consider
  risky, **stop and report that plugin** rather than half-migrating it.
- Do not drop any prescient task. The twin cleanup stays with the owner (the store refuses an
  agent, correctly); the two commands are already in your previous report and the coordinator
  has them.
- Commit locally. Do not push.
