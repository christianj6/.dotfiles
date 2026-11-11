# Report: Discord replies (docs/issue-discord-replies-broken.md)

Committed locally, not pushed. **Not live yet: the bot process has to be restarted. See the end.**

## The doc's diagnosis was half of it: the bot has not been running at all

`bridge.log` shows `DISCORD_BOT_TOKEN missing -- bridge cannot start` every 60 s, from the oldest log entry (2026-11-05 20:59, after a rotation) until now. With no bot there is no gateway, so **no reply could reach any channel**, whichever label it had. Webhook notifications don't need the bot, which is why they kept arriving. (A dead bot gives the same symptom as the doc's cause.)

**Cause:** `load_env()` reads two `.env` files in order:
1. the herdr config dir's;
2. the plugin root's (gitignored).

It skips any key already in `os.environ`. The config dir's `.env` holds a copied template line, `DISCORD_BOT_TOKEN=`, with an **empty** value (file dated 2026-09-15). That empty value got set first, so the real token in the plugin root's `.env` was skipped. I checked this live: a fresh process resolved no token before the fix and does resolve one after it.

**Fix (`common.py`):** an empty value is a template line, not a setting, and no longer shadows a later file. An empty real env var also counts as unset. I did not touch either `.env` file; they hold your credentials.

## The doc's diagnosis, fixed as specified

1. **`resolve_agent(label)`** (`common.py`) resolves from herdr's live listing at each use. First hit wins:
   1. the exact live label;
   2. the project's plain label;
   3. a suffixed label from an older layout (`dotfiles-w6` → dotfiles).

   Within each step, **omp comes first**. This matters beyond the plain channels too: notify posts to **`#dotfiles-wD`** (the suffixed channel that reconcile provisioned). There both panes share the exact label, so the old exact match handed the message to whichever pane herdr listed first, which could be the Claude. `bot.find_agent` now uses this.
2. **Stored `pane_id` is gone.** reconcile no longer writes it, and it removes the stale ones (`wD:p1`, `w5:p8`, …) on its next pass. Nothing in the inbound path ever read it; a test pins that.
3. **The relay replies `→ taken by omp-v36-wdp9 (omp, wD:p9)`** after the ✅. That covers both delivery paths: `agent prompt` and the REPL fallback.

## Acceptance

1. **Live resolution** with today's listing: `dotfiles → omp-v36-wdp9`, `prescient → omp-v36-wdp7`, `heinzel → omp-v36-w5p1d`, `bro → omp-v36-wdp5`. All are omp.
2. `thor-voiceai → omp-v36-wgp1` (single agent).
3. Two-agent projects reach the omp in both the plain and the suffixed channel, and the reply names the agent. This is in code and tests; it can't be checked in Discord until the bot runs.
4. `telia-sms-fraud → None`, so the bot still replies "no live agent for #… right now". `heinzel-exploration` is not folded into heinzel.
5. **A stale `pane_id` cannot affect delivery:** it is never read, it is no longer written, and resolution is live.
6. **`test_resolve.py`: 11 OK**, using a fake listing in herdr's real shape. It covers:
   - two agents in either listing order;
   - a single agent;
   - a suffixed channel;
   - an old-layout suffix;
   - a Claude-only project;
   - no agent;
   - the stale pane id;
   - the empty-template `.env` line.

   `selfcheck.py`: all green.

## To make it live (yours)

The running bot (pid 6874, started 2026-11-02) has the old `load_env` in memory. herdr's `[[startup]]` hook is one-shot, and the bot exits as orphaned if its parent changes, so I can't relaunch it from my shell.

- **Fastest:** delete the two empty lines (`DISCORD_BOT_TOKEN=`, `DISCORD_ALLOWLIST_USER_IDS=`) from the config dir's `.env`. The running loop retries every 60 s, so the old code then finds the plugin root's token. Restart for the new routing after that.
- **Or:** restart the herdr server, so the startup hook runs the new code.

Then a reply in `#dotfiles` should get a ✅ and `→ taken by omp-v36-wdp9 …`.
