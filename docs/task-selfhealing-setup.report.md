# Report: a readable template and a setup that heals itself (docs/task-selfhealing-setup.md)

Committed locally, not pushed.

## Part 1: the template

`config/herdr/plugins/agent-discord/.env.example` is the only `.env.example` in the repo. It now has:
- a section header per service;
- each key at the start of its line, with one trailing comment `# required · …` / `# optional · …`;
- optional keys commented out;
- the "where to put it" prose in one header block at the top, instead of above every key.

**This also needed a loader fix.** With a trailing comment, `KEY=   # required` used to read as the comment text, a non-empty bogus value. `common.load_env` now goes through `parse_env_value()`, which drops a ` #…` tail outside quotes (`tok#en` is kept). The empty-value guard from the previous fix stays.

## Part 2

### 2a. The seed cannot shadow (the bug that cost the day)

**`scripts/env-seed.py <template> <dest>`** replaces setup's `cp`:
- **dest missing:** it writes the template with **every** key commented out, mode 0600, using `O_EXCL`.
- **dest present:** it never rewrites a value. It only comments out an **empty** active key, which carries no secret but shadows a real one in a higher-priority file.
- It prints the key names it changed and never a value.

**I ran it on your live config `.env`.** It commented out the empty `DISCORD_BOT_TOKEN=` / `DISCORD_ALLOWLIST_USER_IDS=`, and no other line changed. That is the self-heal for machines that already ran the old setup. Your token still resolves from the plugin root's `.env`.

### 2b. `scripts/workspace-up`

There is one entry per piece: **lifeview**, **discord-bot**, **prescient** (8765) and **bro** (8766).
- **Starts what is down:** a detached launch from the current code, logging to `/tmp/workspace-up-<piece>.log`.
- **Restarts what is stale:** when the newest mtime of the files a piece runs is later than the process start time from `ps lstart`. Directories count every `*.py` under them.
- **Idempotent:** it does nothing when everything is running and fresh. Tested, and shown live.
- **Options:** `--dry-run` and `--only a,b`.
- **Launch commands:** prescient uses its own launcher's shape (sources `.env`, `gantt serve --port 8765 --no-open`), but starts **only** 8765. `tools/restart-servers.sh` would also kill the 8917 test server. bro uses `.venv/bin/bro serve`.
- **No hard-coded repo paths** (this repo is public). The prescient repo is the parent of `PRESCIENT_DATA_DIR`, and the bro repo is three levels up from `BRO_BIN`. Both come from the env or lifeview's local config, which already holds them, and can be overridden with `PRESCIENT_REPO` / `BRO_REPO`. If either is missing, the summary says "no launcher" and names the key to set.
- **The bot can now run outside herdr:** with `HERDR_DISCORD_DETACHED=1`, the orphan guard is skipped. The flock still prevents a second gateway.

**Wiring:**
- `setup.sh` calls workspace-up after "Setup complete" (non-fatal).
- `workspace-rollout` calls it at the end of a real (non-dry) rollout without changing its exit status. The skill doc says so.

### 2c. Health checks that test what broke

- **discord:** `selfcheck.py --live` checks:
  - the token resolves, printed only as "resolves" or "resolves to nothing";
  - the allowlist is set;
  - every channel of a live project resolves to an agent, via the same `resolve_agent` the bot uses;
  - Discord accepts the token (`GET /users/@me`).

  workspace-up also requires a `bot ready` line in bridge.log since the process started, so "running" means the gateway is up.
- **lifeview:** `hub_token()` finds the token, which is what broke today.
- **prescient:** `/api/health` returns 200 with `write_token.guarded`. **bro:** `/health` returns `{"ok": true}`.

### 2d. The summary

`workspace: N running, N started, N stale, N restarted, N unhealthy, N need you - <what>`, followed by one indented line per item, each with a copy-paste `run:` line (e.g. `run: echo 'DISCORD_BOT_TOKEN=...' >> ~/.config/herdr/plugins/config/dotfiles.agent-discord/.env`). It exits 1 when something needs you.

## Live runs

```
$ scripts/workspace-up --only discord-bot
discord-bot  running (pid 37580 ) up 0s   code 1m   old   ok: token ok, 13 channels resolve, Discord connects   [restarted: code 20m newer than process (bot.py) -> started]
$ scripts/workspace-up --dry-run      (after; second run of discord-bot did nothing)
lifeview     running (pid 35016 ) up 52m  code 55m  old   ok: hub token found
discord-bot  running (pid 37580 ) up 34s  code 2m   old   ok: token ok, 13 channels resolve, Discord connects, bot ready
prescient    running (pid 41226 ) up 1h   code 2h   old   ok: /api/health answers 200
bro          running (pid 25411 ) up 15h  code 1m   old   ok: /health answers 200   [would restart: code 15h newer than process (gate.py)]
workspace: 4 running, 0 started, 1 stale, 0 restarted, 0 unhealthy, 0 need you
```

**After the restart,** the bridge log shows `bot ready as Herdr Integration#7459` at 17:00:07. The new bot's parent is launchd, as the detached launch intends.

**I did not restart prescient or bro.** They are your services, and bro's code was being edited seconds earlier (`code 1m old`): another agent is working in bro. The dry run shows bro as stale; running `scripts/workspace-up` restarts it.

## Acceptance

| # | | Result |
|---|---|---|
| 1 | Templates key-first, trailing comment, optionals commented | PASS (the one `.env.example`). A test seeds every `.env.example` in the repo and finds no live key. |
| 2 | No empty keys seeded; clean-HOME test | PASS. `test_clean_home_seed_then_drop_a_token_and_the_loader_finds_it`: the seed doesn't shadow the plugin-root token, and the appended `DISCORD_BOT_TOKEN=` from setup's copy-paste line is found. |
| 3 | workspace-up: idempotent, starts, restarts by mtime, one line per piece | PASS. Tests run against a fake daemon (start, then a no-op second run; restart after touching the code; dry run touches nothing), plus the live runs above. |
| 4 | setup.sh ends by calling it | PASS (and workspace-rollout does too). |
| 5 | Discord selfcheck fails on an empty token | PASS. `--env-file` holding `DISCORD_BOT_TOKEN=   # required` gives `FAIL token: … resolves to nothing … (run: echo 'DISCORD_BOT_TOKEN=...' >> …)` and `selfcheck: FAILED`, exit 1. This is a test. |
| 6 | The summary names what needs the owner | PASS. Tests cover the no-launcher and unhealthy cases with `run:` lines. |
| 7 | No secret printed | PASS. Grepping for the live token across workspace-up, selfcheck `--live` and the launch logs finds 0. A test checks that env-seed names keys, never values. |

**Suites:**
- `scripts/test_workspace_up.py`: 9 OK.
- agent-discord: `test_resolve.py` 11 OK, `selfcheck.py` all green.

## Noted, not done

- **"thor invisible / work-mode default"** (row 3 of the doc's table) is prescient's setting, not this repo's. Not touched.
- **prescient's server inherits herdr's env from whatever starts it,** according to its launcher's comment. When workspace-up runs from `setup.sh` outside herdr, a prescient it starts has no `HERDR_*` env. Run from a herdr pane, it inherits it. I did not check which prescient features need it.
- **Delegation:** the prescient/bro launch facts came from one read-only subagent. I checked its numbers against the live `ps`/curl output above.
