# REPORT: workspace-up never signals a process that only mentions a piece

Spec: `docs/task-workspace-up-never-kills-shells.md`.

## Headline

- **Guard 1: match the program, not the command line.** A piece is now a process **running**
  its program, read from the process's **exact argv**.
  - The argv comes from the kernel: `sysctl KERN_PROCARGS2` on macOS, `/proc/<pid>/cmdline`
    on Linux. `ps`'s space-joined string is not used, because paths contain spaces
    ("Application Support").
  - `argv[0]` must be a Python interpreter and the script its first non-option argument,
    matched as a **whole, anchored element** (`(?:.*/)?lifeview\.py`). Alternatively the
    script is `argv[0]` itself.
  - Required arguments (`--daemon`, `serve`, …) must be whole elements.
  - `-c` and `-m` never match.
  - An unreadable argv never matches.
  - `Piece.match` stays as a cheap prefilter only.
- **Guard 2: never ourselves, an ancestor, or our group or session.**
  - Ancestors come from walking `ps` parent links up from our pid.
  - Group and session come from `os.getpgid` and `os.getsid` against ours.
  - Every exclusion is **printed**: `lifeview: skipping pid N (our own ancestor)`,
    `(in our own process group)`, `(workspace-up itself)`. A real piece misidentified this way
    stays visible.
  - Both guards apply to everything: judging, the `start()` wait and `stop()`.
- **No piece is special-cased by name.** Every piece declares its program (`script`, `args`),
  and one function, `runs_program()`, decides for all six.
- **The staleness logic is unchanged** (mtime against start, lock holder judged). This change
  only constrains *who* may be signalled.

## Acceptance

### 1. A shell that only mentions the piece is not matched, and the real daemon still is

```
$ bash -c 'echo lifeview.py --daemon; ./scripts/workspace-up --dry-run --only lifeview'
lifeview.py --daemon
lifeview     running (pid 63514 ) up 6m   code 6m   old   ok: hub token found
workspace: 1 running, 0 started, 0 stale, 0 restarted, 0 unhealthy, 0 need you
invoking shell pid 78028 still alive
```

The shell is not even a candidate: its `argv[0]` is `bash`, so there is no skip line. The real
daemon 63514 is found.

**The dangerous case, for real rather than a dry run:** a **stale** daemon, with
`workspace-up` run from a shell that mentions the piece:

```
$ touch …/lifeview.py; bash -c 'echo lifeview.py --daemon; ./scripts/workspace-up --only lifeview; echo "invoking shell pid $$ still alive"'
lifeview.py --daemon
lifeview     running (pid 80930 ) up 0s   code 0s   old   ok: hub token found   [restarted: code 9s newer than process (lifeview.py) -> started]
workspace: 1 running, 0 started, 0 stale, 1 restarted, 0 unhealthy, 0 need you
invoking shell pid 80899 still alive
```

Before this change, that same shape killed my shell twice.

### 2. The lock-holder fix does not regress

`repro.sh` touches the code and puts a hook-like launch in flight. The launch is a real
`python3 lifeview.py --daemon` argv, a sleeper script, in its own session like herdr's hooks.

```
before: holder 78601 (started 15:13:31), all matches: 78601 80166
$ python3 scripts/workspace-up --dry-run --only lifeview
lifeview     running (pid 78601 lock holder; 80166 launch in flight) up 45s  code 1s   old   ok: hub token found   [would restart: code 44s newer than process (lifeview.py)]
workspace: 1 running, 0 started, 1 stale, 0 restarted, 0 unhealthy, 0 need you

before: holder 78601 (started 15:13:31), all matches: 78601 80166 80518
$ python3 scripts/workspace-up --only lifeview
lifeview     running (pid 80587 ) up 0s   code 1s   old   ok: hub token found   [restarted: code 55s newer than process (lifeview.py) -> started]
workspace: 1 running, 0 started, 0 stale, 1 restarted, 0 unhealthy, 0 need you
after: holder 80587 (started 15:14:29), all matches: 80587
```

**Guard 2 caught a case I had set up by accident.** My first version of `repro.sh` started the
stand-in as a child of the same script, so it was in `workspace-up`'s process group. It was
printed `lifeview: skipping pid 78490 (in our own process group)` and not stopped, while the
stale holder was restarted. That is the guard doing its job.

### 3 and 6. Healthy: `--dry-run`, then the full run

I ran both from my pane. A shell-free run from the coordinator's pane exercises the same code.
`--dry-run`: `6 running, 0 started, 0 stale, 0 restarted, 0 unhealthy, 1 omp stale`. Then the
full run:

```
lifeview     running (pid 80930 ) up 1m   code 1m   old   ok: hub token found
discord-bot  running (pid 20900 ) up 28m  code 31m  old   ok: token ok, 24 channels resolve, Discord connects, bot ready
omp-watch    running (pid 68815 ) up 7m   code 31m  old   ok:
claude-name  running (pid 20353 ) up 29m  code 31m  old   ok:
prescient    running (pid 68116 ) up 2h   code 1d   old   ok: /api/health answers 200
bro          running (pid 24490 ) up 27m  code 20h  old   ok: /health answers 200
omp w5:p1R   topical          pid 49506  up 4d   ok: window 1000000, threshold 500000
omp w5:p1T   heinzel          pid 75495  up 4d   ok: window 1000000, threshold 500000
omp wD:p5    bro              pid 83146  up 21h  ok: window 1000000, threshold 500000
omp wD:p7    prescient        pid 452    up 21h  ok: window 1000000, threshold 500000
omp wD:p9    .dotfiles        pid 41690  up 21h  ok: window 1000000, threshold 500000
omp wG:p1    thor-voiceai     pid 84434  up 21h  ok: window 1000000, threshold 500000
omp wG:p6    ai-assisted-dev  pid 80155  up 7d   STALE: threshold 660000 vs config 500000
omp wG:pC    knowledge-graph  pid 4499   up 3d   ok: window 1000000, threshold 500000
omp wG:pE    market-research  pid 37479  up 3d   ok: window 1000000, threshold 500000
omp wG:pG    telia-sms-fraud  pid 14852  up 2d   ok: window 1000000, threshold 500000
workspace: 6 running, 0 started, 0 stale, 0 restarted, 0 unhealthy, 1 omp stale, 1 need you - omp wG:p6 (ai-assisted-dev): ...
```

- The shell that launched this run had the piece regexes in its own command line, for the
  `pgrep` count after it, and it survived.
- **Daemon counts:** lifeview 1, claude-name 1, agent-discord 1, omp-watch 1.
- **All six real pieces match on their kernel argv.** For example, lifeview is
  `[…/Python, lifeview.py, --daemon]`, bro is `[…/Python, …/.venv/bin/bro, serve]`, and
  prescient is `[…/Python, .venv/bin/prescient, gantt, serve, …]`.

### 4 and 5. Tests (`scripts/test_workspace_up.py`, 36 tests, all passing)

New class `ShellNeverKilled`:

- **`test_the_real_daemon_shapes_match`:**
  - the framework `Python` as `argv[0]`;
  - an absolute script path;
  - the options `-u` and `-X dev`;
  - the script exec'd as `argv[0]`.
- **`test_a_shell_that_mentions_the_piece_is_not_it`:**
  - `bash -c 'echo lifeview.py --daemon; …'`;
  - `zsh -c "pgrep -f 'lifeview.py --daemon'"`;
  - `zsh -c "python3 lifeview.py --daemon"`, a shell that would *run* it;
  - `pgrep`, `git commit -m "fix lifeview.py --daemon lock"`, `nvim`, `tail -f`;
  - `python3 -c …` and `-m …`;
  - `notlifeview.py`, `lifeview.py.bak`, a missing `--daemon`, `--daemon=no`;
  - an empty or unreadable argv.
- **`test_ancestors_and_self_are_protected`:** the parent chain walked from a fake table.
- **`test_a_table_whose_only_matches_are_us_and_our_parent_yields_no_actions`** (acceptance
  4): even when self and parent look exactly like the piece, nothing is returned to signal, and
  both skip lines are printed.
- **`test_our_process_group_or_session_is_excluded_visibly`**.
- **`test_a_real_daemon_elsewhere_is_still_found`:** the real daemon is returned. The
  mentioning shell is not even a candidate, so there are no lines.
- **`test_unreadable_argv_never_matches`**.
- **`test_proc_argv_reads_the_exact_argv_of_a_live_process`:** an argument with a space comes
  back intact.
- **`test_every_piece_names_its_program`**.

The existing `WorkspaceUp`, `Serving` and `ServingLive` tests stay green. Their fake piece now
declares its program (`fake_daemon\.py` plus its marker argument).

## Is `repro.sh` still needed?

**For safety, no.** The guards make it safe to run `workspace-up` from any command line,
including one that names a piece. Section 1 shows this for real, not just as a dry run.

**For reproducing the lock-holder case, yes, and I kept it.** It sets up a stale holder plus
an in-flight launch in one step. It needed one change: its old stand-in,
`python3 -c 'sleep' lifeview.py --daemon`, is correctly *no longer* a piece because of `-c`.
It now runs a sleeper **script named `lifeview.py`** in its own session, which matches what a
herdr hook launch looks like at the argv level. It lives in my scratchpad, not the repo.

## Limits, stated

- **Bare script names can still collide.** lifeview and claude-name are launched with relative
  script names (`python3 names.py --daemon`), so their program is matched by basename plus
  `--daemon`. Another project's `python3 names.py --daemon` would match. Shells, editors,
  `git` and `pgrep` can never match. The two path-anchored pieces are agent-discord
  (`agent-discord/bot.py`) and omp-watch (`omp-watch/watch.py`). Checking the process cwd would
  close this; I did not add it.
- **A piece started by `workspace-up`'s own invoking group is skipped, visibly.** Nothing in
  the normal flow does this: `workspace-up` starts pieces with `start_new_session=True`, and
  herdr's hooks run in herdr's own session.
- **`bot_connected()`** still finds the bot by regex. It only runs `lsof`, never signals, so I
  left it unchanged.

## Changed files

- `scripts/workspace-up`:
  - `Proc.ppid`, and `processes()` now reads the ppid;
  - new `proc_argv()`, `runs_program()`, `protected_pids()`, `same_group()` and
    `piece_procs()`;
  - new `Piece.script` and `Piece.args`, set on all six pieces;
  - `run()` and `start()` use `piece_procs()`.
- `scripts/test_workspace_up.py`: `ShellNeverKilled`, and the fake piece declares its program.
- `config/claude/settings.json`: still an uncommitted change I did not make; not in the
  commit.
