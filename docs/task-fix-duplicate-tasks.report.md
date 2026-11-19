# REPORT: duplicate auto tasks — the lifeview lock now survives path replacement

Spec: `docs/task-fix-duplicate-tasks.md`.

## Headline

- **Fixed:**
  - the lock now lives outside `/tmp`, in
    `~/.local/state/herdr/plugins/dotfiles.lifeview-fallback/lock`;
  - it is inode-checked on acquire;
  - the running daemon re-checks it every tick and re-takes the path, or exits if someone else
    holds it.
- **One daemon is running:** `pgrep -f 'lifeview.py --daemon' | wc -l` → **1**.
- **Proven live:** with the lock file replaced, a second daemon **exits**. Both race orders
  ended with exactly one daemon.
- **The first direct owner message after the fix made exactly one task:** `tk-609e5d24e36b`,
  one hub row and one `opened` log line.
- **Twins NOT dropped. prescient refuses:** `task: only the owner drops a task`. I did not
  override that with `--by owner`, which would forge the owner's provenance. The two open pairs
  and the exact commands are below.
- **The same `/tmp` lock fault exists in other plugins, and is live in claude-name now:** two
  daemons are running. I did not touch them (spec: no other plugin). See "Outside the spec".

## 1. The lock (`config/herdr/plugins/lifeview-fallback/lifeview.py`)

- **`LOCK_PATH`** is now `~/.local/state/herdr/plugins/dotfiles.lifeview-fallback/lock`, a
  fixed path. It deliberately does not follow `HERDR_PLUGIN_STATE_DIR`: a launch from another
  context, such as `workspace-up` run from a pane or by another plugin, must find the same
  lock. The parent directory is created on demand.
- **`SingletonLock`** replaces the bare open + flock. It is still an flock, not a pidfile.
  - **`acquire()`:** open, then `flock(LOCK_EX|LOCK_NB)`, then compare
    `(st_dev, st_ino)` from `stat(path)` and `fstat(fd)`. If the path was replaced between open
    and flock, it refuses. On success it writes the pid.
  - **`keep()`:** called at the top of every tick in `run()`. If the path still names our
    inode, nothing happens.
    - If the path was removed or replaced, it tries to take the path. If it succeeds, it logs
      `was removed or replaced; re-took it` and carries on.
    - If someone else holds the path, it logs `now held by another instance; exiting` and
      `run()` returns.
- **Why `keep()` is needed:** an inode check at acquire time alone cannot make a later
  newcomer exit. After a prune, the newcomer creates a fresh file, locks it, and its own check
  passes. Making the holder re-take the path within one tick (10 s) is what makes the next
  launch hit a held lock. If a newcomer wins that race, the old holder exits instead. Either
  way, one daemon survives.
- **Not done:** the spec's optional third item, checking whether the recorded pid is alive on
  a failed acquire. With `keep()` in place, a failed acquire means the path really is held by a
  live flock holder, so there is no stale case to take over.

## 2. Exactly one daemon

Before the fix:

- pid 14825 (Nov 12) held `/private/tmp/lifeview-fallback.lock` on inode 92236289;
- pid 47089 (Nov 18) held the same path on inode 108131618;
- both carried `HERDR_PLUGIN_ID=dotfiles.lifeview-fallback` and ran the old code.

I sent `kill` to both, rather than keeping 47089, because 47089 ran the old code too. I let
herdr's own `[[events]]` hook relaunch it, so it got the real plugin environment. Result: one
daemon, pid 95701, on `~/.local/state/…/lock`. Then the race below replaced it with **96401**,
the survivor. The count now is `pgrep -f 'lifeview.py --daemon' | wc -l` → **1**.

## Acceptance 2: replace the lock while the daemon runs, then start a second

**Run 1:**

```
before: ino 110207177
rm lock; : > lock          -> ino 110207334 (empty, unlocked)
  (an [[events]] launch won the race and locked the new file: pid 96401)
log: 14:37:27 lock path …/lock now held by another instance; exiting     <- old holder 95701 stepped aside
python3 lifeview.py        -> exit=0 (second instance exits on the lock)
python3 lifeview.py --daemon; sleep 3 -> count=1 pids=96401
```

**Run 2 (no race this time):**

```
holder before=96401; rm lock; : > lock; sleep 12
log: 14:37:54 lock path …/lock was removed or replaced; re-took it        <- holder re-took the path
holder after=96401, lockfile=96401
python3 lifeview.py        -> exit=0
count=1
```

This is the macOS `/tmp`-prune scenario in both orders. Before the fix, the second launch ran.
Now it exits.

## Acceptance 3: one task per direct message

- The first owner message after the restart, to topical at 14:37:33, made
  **`tk-609e5d24e36b`**, the only `auto:` row created since 14:37.
- The daemon log has exactly **1** line for it: `grep -c 'tk-609e5d24e36b opened'` → 1.
- For contrast, the last message before the fix, at 14:33:43, made the twins
  `tk-6d88ec217e15` and `tk-5edb44ae05ee` in the same second.

## 3. The duplicate twins: found, not dropped

**What counts as a twin:** a group with the same project, target, text and `created`. There
are 45 groups: 44 pairs and one triple.

**The 2 open pairs: drop the newer `seq` (blocked).** Both copies of each are still `queued`
and unchanged; I re-read them before trying:

| keep | drop (newer seq) | project | created (UTC) |
|---|---|---|---|
| `tk-c29019fd7689` (s3509) | **`tk-0e36d28399f3`** (s3511) | thor-voiceai | 13:32:40 |
| `tk-6d88ec217e15` (s3513) | **`tk-5edb44ae05ee`** (s3515) | dotfiles | 13:33:43 |

`prescient task done <id> --resolution dropped --note …` → `task: only the owner drops a task`.
Nothing changed. My first attempt didn't even reach prescient, because zsh passed both ids as
one argument, and prescient answered `no task` with no change. **The owner can run:**

```
prescient task done tk-0e36d28399f3 --resolution dropped --note "duplicate of tk-c29019fd7689: second lifeview daemon (lock defeated by /tmp pruning)"
prescient task done tk-5edb44ae05ee --resolution dropped --note "duplicate of tk-6d88ec217e15: second lifeview daemon (lock defeated by /tmp pruning)"
```

**Left as they are, and reported:**

- **37 auto+owner pairs that are already `done`** (Nov 18 08:43 onward; the second daemon
  started Nov 18 08:25). They are out of the owner's column already, and dropping one would
  rewrite a resolution the owner gave.
- **5 pairs where the two copies are in different states**, which the spec calls ambiguous:
  - `tk-dff51ea28b1a`/`tk-229aa28ff030`
  - `tk-5629e2719ecc`/`tk-4b8b97497551`
  - `tk-d38c5623d419`/`tk-ddcbaa3b8d58`
  - `tk-f5c4e88c139b`/`tk-1102d95d2a24`
  - `tk-30b3f716474f`/`tk-3e7c800f0279`
- **topical `tk-07d8ab7cb055` (done/dropped) and `tk-053455ddd36c` (ready):** the owner sees
  only one card here.
- **2 older groups (Nov 3 and Nov 7) that are not `auto:`.** They predate this bug and are
  already done.

## Tests

`python3 test_lifeview.py`: 141 tests, all passing. The new `Singleton` class covers:

- **(a)** a second instance on the same inode is refused, and the holder's `keep()` stays true;
- **(b)** when the path is replaced, the holder re-takes it, and a later instance is refused;
- when the path is removed, the holder re-takes it;
- when a newcomer wins the replaced path, the old holder's `keep()` is false, so it exits;
- `acquire()` refuses a path that was replaced between open and flock;
- `run()` returns before any tick once the lock is lost;
- `LOCK_PATH` is not under `/tmp`.

## Outside the spec (reported, not touched)

- **claude-name has two daemons right now:**
  - 14514 (Nov 12) holds `/tmp/claude-name.lock` on an orphaned inode, 92236287;
  - 47069 (Nov 18) holds the current file, inode 108131616.

  This is the same `/tmp`-prune fault.
- **agent-discord's lock file `/tmp/herdr-agent-discord.lock` is gone.** The bot (14457) holds
  the orphaned inode 92236290, so the next launch, for example from `workspace-up`, would start
  a **second bot**.
- **omp-watch** (`/tmp/omp-watch.lock`) is fine for now: one process, and the path still names
  its inode. It has the same weakness.
- **`LOG_PATH`** is still `/tmp/lifeview-fallback.log`. 14825's log went to an orphaned inode
  as well, which is why its copies of the twin opens never appear in the log. Moving it changes
  where people look, so I left it.
- `SingletonLock` could be shared by all four plugins. That is a follow-up for the coordinator
  to scope.
