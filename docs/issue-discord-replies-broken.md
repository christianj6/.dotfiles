# Discord replies stopped working — notifications still do

Owner: *"I keep getting them and they seem accurate, but if I try to send a message back, it
seems to not work now."*

Reproduced and root-caused. **Out and in use different lookups; the inbound one is broken.**

## The bug

`channels.json` stores 44 channels keyed by **plain project label**:

```
dotfiles  prescient  heinzel  thor-voiceai  telia-sms-fraud  heinzel-exploration
```

`agent_label_map()` builds labels from **live cwd**, and when a project has **more than one
agent** (which is every modern project — an omp plus its Claude) it suffixes **both**:

```python
else:
    for pane_id, cwd, ws in entries:
        out[pane_id] = (f"{label}-{ws or 'x'}", cwd)
```

Actual live labels right now:

```
wD:p9   dotfiles-wD      wD:pA   dotfiles-wD
wD:p7   prescient-wD     wD:pC   prescient-wD
w5:p1D  heinzel-w5       w5:p1A  heinzel-w5
wD:p5   bro-wD           wD:p6   bro-wD
wG:p1   thor-voiceai     <- single agent, so it keeps the plain label
```

So `find_agent("dotfiles")` matches **nothing** — the map only has `dotfiles-wD`. A reply in
`#dotfiles`, `#prescient`, `#heinzel` or `#bro` fails; `#thor-voiceai` works, because that
project still has one agent.

**That is exactly the symptom.** Outbound notifications use the stored `webhook_url` and never
call `find_agent`, so they keep working. Inbound needs `find_agent(label)` and silently falls
through:

```python
pane_id, _ = find_agent(label)
if not pane_id:
    await message.reply(f"no live agent for #{label} right now.")   # or a silent return
```

It started when projects gained a second pane (the omp + Claude pairing), not at any single
commit — which is why it felt like "it used to work".

## The fix (two parts, both needed)

**1. Resolve a label to a live agent, not an exact string.** `find_agent` should accept the
plain label and match the suffixed forms with a defined preference:

```python
def find_agent(label):
    """(pane_id, cwd) for the agent a channel means.

    Preference, because a project usually has TWO agents: the coordinator
    (omp) first — it is the one that owns the task and answers for the
    project — then any other ('label-<ws>' with no further suffix). Exact
    match still wins when it exists (a single-agent project).
    """
```

The coordinator-first preference matters: a Discord message is a request to the *project*, and
the omp is the agent that decides what happens to it. Replying to its Claude instead would
bypass the coordinator — the same mistake `tk-a49ea85f1d54` corrected in bro.

**2. Reconcile `channels.json` with live labels.** The stored entries also carry stale
`pane_id`s (`wD:p1`, `w5:p8`, `w7:p1P`, `w5:p14`) from an older workspace layout. Either
refresh them from the live map at load, or stop storing `pane_id` at all and always resolve —
a stored pane id goes stale on every rollout, which is the `83173fa` class.

## Acceptance

1. `find_agent("dotfiles")` returns a live pane (the omp), as do `prescient`, `heinzel`, `bro`.
2. `find_agent("thor-voiceai")` still works (plain label, single agent).
3. A message in a project channel with two agents reaches the **coordinator**, and the reply
   says which agent took it.
4. A channel whose project has no live agent still says so plainly — that message exists and
   is correct.
5. A stale `pane_id` in `channels.json` does not prevent delivery.
6. A test for the two-agent case and the single-agent case, using a fake herdr listing.

## Note

This is the **third** instance of one pattern today: a lookup keyed on a name that changes
underneath it. The others were the hub's agent-keyed coverage (items carry `agent: null`) and
`omp-peer` failing on `omp-v25` after the v35 roll (`83173fa` class). The durable rule is the
same each time: **resolve at use time from live state; never trust a stored identity.**

---

## The actual blocker the worker found, and it overrides the label bug

The label fix was necessary but not sufficient. **The bot was never starting at all.**

`load_env()` reads two `.env` files, `CONFIG_DIR` first, then the plugin root. The config-dir
one is a **template** containing:

```
DISCORD_BOT_TOKEN =
DISCORD_ALLOWLIST_USER_IDS =
```

An empty value was being loaded as a setting, so it **shadowed the plugin root's real token**
(set since 2026-09-05, 72 chars). The bot read `""`, logged `DISCORD_BOT_TOKEN missing --
bridge cannot start`, and exited. Notifications kept arriving because `notify.py` uses the
stored `webhook_url` and never needs the bot.

Fixed in `common.load_env`: *"An EMPTY value is a template line, not a setting: it must not
shadow a later file's real value."* Verified:

```
env -u DISCORD_BOT_TOKEN  python -c 'common.load_env(); print(len(os.environ["DISCORD_BOT_TOKEN"]))'
  -> <SET 72 chars>
```

## What I verified after restarting the bot

The old process was **pid 6874, started 2026-11-02 — nine days old**, i.e. it predates both
the template and the label fix. Stopped it and started the current code:

- new pid **90315**, alive, one live TCP connection (Discord gateway connected)
- `resolve_agent(label)` for all five project channels returns the **omp**, which is the
  coordinator — a Discord message is a request to the project, and the omp decides what
  happens to it:

```
dotfiles     -> omp-v36-wdp9  (wD:p9)
prescient    -> omp-v36-wdp7  (wD:p7)
heinzel      -> omp-v36-w5p1d (w5:p1D)
thor-voiceai -> omp-v36-wgp1  (wG:p1)
bro          -> omp-v36-wdp5  (wD:p5)
```

## For the owner

Replying in any agent channel should now reach that project's coordinator. If a channel still
says *"no live agent for #… right now"*, that message is now accurate rather than masking a
lookup failure — it means the project genuinely has no agent up.

## Two residuals

1. **The config-dir `.env` template should not ship empty keys that look like settings.** The
   load guard is the right fix; the template is better with them commented out (`#DISCORD_BOT_TOKEN=`),
   so nobody copies it and wonders why it shadows.
2. **Nine days without a restart** is the same omission as the lifeview daemon: the bot is a
   long-running process, so shipping a fix does not make it live. Worth adding the bot to
   whatever restarts things after a rollout.
