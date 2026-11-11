# Self-healing setup: verified by running it

Owner's goal: *"i go on a new machine run setup, drop in my secrets (as instructed by the setup
script) and then all the workspace pieces just work and are self healing."*

## `scripts/workspace-up` — the shape asked for

```
lifeview     running (pid 35016) up 56m  code 58m old  ok: hub token found
discord-bot  running (pid 37580) up 3m   code 5m  old  ok: token ok, 13 channels resolve,
                                                         Discord connects, bot ready
prescient    running (pid 41226) up 1h   code 2h  old  ok: /api/health answers 200
bro          running (pid 49511) up 0s   code 59s old  ok: /health answers 200
             [restarted: code 15h newer than process (voicebridge.py) -> started]
workspace: 4 running, 0 started, 0 stale, 1 restarted, 0 unhealthy, 0 need you
```

**It found bro stale and restarted it** — fifteen hours of code newer than the process, which
is exactly the class of failure that kept biting (the nine-day bot, the pre-fix daemon). The
rule is code **mtime vs process start**, so there is no version file to forget to bump.

## The health check tests the thing that broke

`selfcheck.py` alone is syntax only — it said *"all green"* while the bot could not start, which
is the whole reason this task existed. `selfcheck.py --live` is the real one, and I proved it
both ways:

```
$ selfcheck.py --live
  PASS channel #prescient-wD -> omp-v36-wdp7 (omp)
  PASS connect: Discord accepts the token (bot Herdr Integration)
  selfcheck: all green                                    exit 0

$ DISCORD_BOT_TOKEN=invalid selfcheck.py --live
  FAIL connect: Discord answered 401 - token rejected
  selfcheck: FAILED                                       exit 1
```

And `workspace-up` propagates it instead of swallowing it:

```
discord-bot  running  UNHEALTHY: connect: Discord answered 401 - token rejected
workspace: 4 running, ..., 1 unhealthy, 1 need you - discord: connect: Discord answered 401
```

**That is the chain that was missing**: a broken piece now says so, names itself, and exits
non-zero.

## The seed can no longer shadow a secret

`setup.sh` used to `cp .env.example "$DISCORD_CFG_DIR/.env"` — copying **empty** keys into the
higher-priority file, which is what hid the real token for days. Now `scripts/env-seed.py`:

- dest missing → writes the template with **every key commented out**; verified: zero active
  keys in the output, so nothing can shadow;
- dest present → **never rewrites a value**, only comments out *empty* keys in place. Verified:
  a real `DISCORD_BOT_TOKEN=…` survives a re-run byte for byte.

## What a new machine now does

`setup.sh` → venv, plugin link, a seed with nothing live, and `workspace-up` at the end. The
owner fills in secrets where the seed tells him to; the next `workspace-up` reports
`0 need you` or names exactly which secret is missing.

## Residual

- **`selfcheck.py` without `--live` is still the syntax-only version** and still prints
  "all green". Any caller that runs it bare gets a green light that means nothing. Worth making
  `--live` the default, or renaming the cheap one to `--syntax`.
- The summary is only as good as the checks behind it: prescient and bro are probed with an
  HTTP health endpoint, which proves they answer but not that they answer *correctly*.
