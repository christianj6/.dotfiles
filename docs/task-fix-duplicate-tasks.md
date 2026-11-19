# TASK: two auto-tasks per agent turn — the singleton lock is defeated by /tmp pruning

Owner: *"if i give a message directly to an agent it gets two duplicate tasks that i see
here in prescient … figure it out and fix it."*

## Cause (measured, do not re-derive)

Two `lifeview.py --daemon` processes are alive, **both holding a flock on the same path
but a different inode**:

| pid | started | inode it locked |
|---|---|---|
| **14825** | Nov 12 07:06 | **92236289** |
| **47089** | Nov 18 08:25 | **108131618** |

`LOCK_PATH = "/tmp/lifeview-fallback.lock"`. macOS periodically prunes `/tmp`, so the
file 14825 locked was **unlinked**, freeing the pathname but not the inode. When 47089
started it created a *new* file at that path and its `flock` succeeded — so
`acquire_singleton_lock()` told both processes they were the singleton.

Both then do the same work on the same agent, twice:

```
14:33:43 bro tk-6d88ec217e15 opened (auto) for omp-v36-wdp9: work session: 1 tool calls, 13s
14:33:43 bro tk-5edb44ae05ee opened (auto) for omp-v36-wdp9: work session: 1 tool calls, 13s
```

Verified in the hub too — every duplicate pair shares text **and** `created` to the
second: `tk-5edb44ae05ee`/`tk-6d88ec217e15` (dotfiles), `tk-0e36d28399f3`/`tk-c29019fd7689`
(thor-voiceai), `tk-053455ddd36c`/`tk-07d8ab7cb055` (topical), and older pairs in `done`.

**So it is not a create-path bug and not a dedupe bug: the lock is not a lock.** A
single daemon would create one task; the second copy comes from the second process.

## Fix — two parts, both required

### 1. Make the singleton lock survive path replacement

An flock on a *path* is only mutual exclusion while the inode is reachable. Options, in
preference order:

- **Put the lock where `/tmp` pruning does not reach** and that is per-user and
  per-plugin-version-safe — e.g. `Path.home() / ".local/state/herdr/plugins/dotfiles.lifeview-fallback/lock"`,
  creating the directory with `mkdir -p` semantics first. This is the real fix.
- **Belt and braces: verify the holder is alive and is us.** After acquiring, re-open the
  path and compare `os.fstat(fd).st_ino` against `os.stat(LOCK_PATH).st_ino`; if they
  differ, the path was replaced under us → exit. Cheap, and it makes the failure loud
  rather than silent.
- Also record the pid and, on a *failed* acquire, check whether the recorded pid is alive
  and is a `lifeview.py` process; a stale pid means take over (the current code just
  exits, which is safe but hides the "two live daemons" state).

**Do not** switch to a pidfile-only scheme — a pidfile cannot be atomic against a crash,
and the owner already ate the recovery cost of a foreign claim today.

### 2. Kill the extra daemon, and make the start path idempotent

- Both hooks (`[[startup]]` and `[[events]]`) launch `python3 lifeview.py --daemon`, so
  every event spawns a process that is *supposed* to exit on the lock. With the lock
  fixed, that becomes true again.
- After the fix, ensure exactly **one** daemon runs: kill 14825 (the older, holding the
  orphaned inode), confirm 47089 survives or restart cleanly, then verify
  `pgrep -f "lifeview.py --daemon" | wc -l` → **1**.

### 3. Report duplicates, do not delete them silently

The owner sees duplicate cards. Clean up **only the obvious auto-created twins** —
pairs with identical text and identical `created`, where both are `auto:` and `origin=owner`
— by dropping the *newer id* of each pair with a note naming this bug. Do not touch
anything else, and **never delete a row silently**: the pattern that damaged data earlier
this session was a probe delete that shared an id with a real task. If a pair is ambiguous
(different state, one already `working`/`done`), leave it and report it.

State the list of ids you dropped in the report.

## Acceptance

1. `pgrep -f "lifeview.py --daemon" | wc -l` → **1**.
2. Proven single-instance: delete/replace the lock file while the daemon runs, start a
   second daemon, and confirm the second **exits** rather than running (this is the exact
   macOS `/tmp`-prune scenario). Show the command and the result.
3. Owner's next direct message to an agent produces **exactly one** auto task. Prove it
   with a fresh hub row and the daemon log line count for that open.
4. Duplicate pairs cleaned up as described, with ids listed in the report.
5. Tests: the lock logic must have a test covering (a) same-inode second instance exits,
   (b) replaced-path second instance exits. Keep the existing tests green.

Commit locally. Do not push. Do not touch any other plugin.
