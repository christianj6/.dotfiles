# TASK: a template you can read, and a setup that heals itself

Owner, 2026-11-11: *"maybe adjust the template so that they don't all begin w the same string
i gotta read. also try to make sure all of this kind of stuff is automatic and self healing.
goal is i go on a new machine run setup, drop in my secrets (as instructed by the setup script)
and then all the workspace pieces just work and are self healing."*

Two asks. The first is small. The second is the real one, and today gave us three concrete
failures to design against.

## Part 1 — the template, readable at a glance

Today `.env.example` is one wall of `#` prose where every entry begins the same way, so the
eye has nothing to land on. Restructure so the **keys** are the visual anchor and the prose
sits under each one, not above:

```
# ─── Discord ────────────────────────────────────────────────────────────
# What: the bridge bot that relays your messages into agent channels.
# Without it: notifications still arrive (webhooks); replies do nothing.

DISCORD_BOT_TOKEN=            # required · bot token from discord.com/developers
DISCORD_ALLOWLIST_USER_IDS=   # required · your Discord user id, else nobody can relay
#DISCORD_GUILD_ID=            # optional · only if the bot is in 2+ servers
#DISCORD_CATEGORY_NAME=herdr agents
#DISCORD_NOTIFY_WEBHOOK=      # optional · fallback before channels exist
```

Rules: a section header per service, the key first on the line, one short trailing comment
saying what it is and whether it is required, and **optional keys commented out** so copying
the file cannot shadow anything. Same treatment for every `.env.example` in the repo.

## Part 2 — self-healing, designed against what actually broke

A new machine running `setup.sh` should end with every piece **working**, and any piece that
breaks later should fix itself or say so loudly. Three failures from today are the test cases:

| what broke | why | what would have caught it |
|---|---|---|
| Discord replies dead | setup **copied an empty template** into the config dir, shadowing the real token | setup writing a *seed* that cannot shadow; a health check |
| lifeview auto-task dead | daemon predated the code | restart-on-deploy, and a health check that notices |
| thor invisible | work mode default was off | a default that matches the owner's intent, and a visible "N hidden" |

So the rule that falls out: **every long-running piece needs (a) a way to be started by setup,
(b) a way to be restarted when its code changes, (c) a health check that notices it is wrong.**
None of the three had all three.

### 2a. Secrets: seed, never shadow

Fix the bug class, not just the instance:

- `setup.sh` must **not** copy a template containing empty keys into a live config location.
  Write a seed with the keys **commented out**, or write only the sections that are genuinely
  optional. An empty key in a higher-priority file is a footgun that already cost a day.
- Keep the `load_env` guard (empty value is a template line, not a setting) — belt and braces,
  because the next template someone copies may still have one.
- Setup should **end by telling the owner exactly what to fill in**, with a copy-paste line
  that does not require reading prose: `run: echo 'DISCORD_BOT_TOKEN=...' >> <path>`.

### 2b. Long-running pieces: one launcher, restart on change

There are at least four: the **lifeview daemon**, the **Discord bot**, **prescient's server**
(8765), and **bro serve**. Today each was started by hand at some point and then left running
for days or weeks. Introduce one command — `scripts/workspace-up` (or a herdr startup hook,
whichever is honest) — that:

- starts anything not running, **from the current code**;
- restarts anything whose **code is newer than its process start** (mtime of the file it
  runs vs the process's start time — no version file to forget);
- is **idempotent**: run it twice, nothing happens the second time;
- prints one line per piece: `discord bot   running (pid …)   code 3h old   ok`.

`setup.sh` calls it at the end. Rolling panes calls it after the roll. That single change
would have fixed both the nine-day-old bot and the stale daemon.

### 2c. Health checks that are real

`selfcheck.py` for Discord today only checks that the files parse — it said "all green" while
the bot could not start. A health check must test the thing that matters:

- **resolves the token** (and never prints it),
- **resolves every configured channel to a live agent** — the exact lookup that was broken,
- **connects** (or reports that it did not),
- and is wired into `workspace-up` so "running" means "working".

Same shape for the others: lifeview `--explain` already has the bones (it caught the label
bug once pointed at the right pane); prescient and bro need a one-line "am I serving" probe.

### 2d. Report, do not guess

At the end of `workspace-up`, one summary either way:

```
workspace: 5 running, 0 stale, 1 needs secrets (discord: DISCORD_BOT_TOKEN)
```

If something cannot self-heal — a missing secret, a service with no launcher — it must say so
in that summary. Silent is the failure mode we keep being bitten by.

## Acceptance

1. `.env.example` files are restructured per the rule above (key first, trailing comment,
   optionals commented out) and the owner can scan them without reading prose.
2. `setup.sh` seeds no config file containing empty keys; a fresh run cannot shadow a real
   secret. Test: seed on a clean HOME, drop a token in the documented place, confirm the
   loader finds it.
3. `scripts/workspace-up` exists, is idempotent, starts what is down, restarts what is stale
   by code-mtime vs process-start, and prints one line per piece.
4. `setup.sh` ends by calling it.
5. The Discord selfcheck fails when the bot cannot resolve its token or any channel — prove
   it by pointing it at an empty token and showing the failure.
6. A summary line names anything that needs the owner (missing secret, no launcher).
7. Nothing prints a secret value.

## Order

1. Template restructure (cheap, visible, yours).
2. `load_env` guard is already in — keep it.
3. The seed fix in `setup.sh` (this is the bug that cost the day).
4. `workspace-up` + the honest selfcheck.
5. Wire both into `setup.sh` and the rollout.

Item 3 on its own makes a new machine correct. Item 4 is what keeps it correct.
