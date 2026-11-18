# Compaction still not working — three live states, only two correct

Owner: *"preemptive compaction doesnt seem working for the omp panes agents are still getting up
to 800+."*

The config is right. **The running processes are not.** Measured across every live omp pane:

| pane | pid | started | `contextWindow` | `thresholdTokens` | verdict |
|---|---|---|---|---|---|
| **prescient** | 23590 | Nov 12 07:12 | **0** | **0** | **never compacts** |
| **bro** | 23795 | Nov 12 07:12 | **0** | **0** | **never compacts** |
| thor-voiceai | 24105 | Nov 12 07:13 | 1000000 | **660000** | the *old* 66% |
| heinzel | 75495 | Nov 15 09:05 | 1000000 | 500000 | correct |
| telia-sms-fraud | 14852 | Nov 17 12:40 | 1000000 | 500000 | correct |

Config as committed (`7ce1a54`, Nov 13 10:17): `thresholdTokens: 500000` and
`modelOverrides.<model>.contextWindow: 1000000`. A fresh process reads it correctly —
`omp models` reports 1M for both opencode-go models, and pid 14852 logs
`contextWindow:1000000, thresholdTokens:500000`.

**So the setting works; three of five panes are running code from before it existed.** That is
the same "shipped but not live" omission as the lifeview daemon, the Discord bot, and `VERSION`
— now the fourth instance, and this one the owner notices as a symptom rather than a theory.

## Why 800k+ happens

For **prescient and bro**, `contextWindow: 0` means the guard
`if (window <= 0) return false` short-circuits before any threshold is consulted — **no
percentage and no token count can apply**. They grow until the provider rejects the prompt and
an overflow recovery kicks in. That is the 800k+ the owner is seeing.

## The fix

**Immediate: restart those panes' omp.** Three panes, in the order that matters: prescient and
bro (never compact — the urgent ones), then thor (compacting at the wrong point).

Use the yarepl restart path the rollout uses (`/exit` via nvim chansend, then `yarepl_start`),
pane by pane, and confirm each afterwards by reading its log:

```
contextWindow:1000000, thresholdTokens:500000
```

Not `workspace-rollout`: it reports `up-to-date` because the panes are already v36 and this is
not a version problem — the same trap as the wedged-claim pane.

**Durable: `workspace-up` must cover omp panes.** It already restarts stale services, and it
compares **code mtime against process start**. A pane's omp process carrying an older
`thresholdTokens` than the config is exactly that class of staleness. Concretely:

- for each omp pane, compare the live `thresholdTokens`/`contextWindow` in its log against what
  `omp models` and `config.yml` now say;
- if they disagree, report it — `prescient omp pane: threshold 0 vs config 500000 (restart needed)`
  — and restart it, or at minimum name it in the summary line the owner already reads;
- this closes the fourth instance of the pattern rather than the fourth symptom.

## Acceptance

1. All five live omp panes log `contextWindow:1000000, thresholdTokens:500000`.
2. A pane left stale on purpose is **named** by `workspace-up` (not silently tolerated).
3. `workspace-up` exits non-zero or prints `N need you` when an omp pane's threshold disagrees
   with the config.
4. Nothing compacts later than before: 0 → 500k for prescient/bro, 660k → 500k for thor.

---

## Fixed and verified, plus a false positive in the new check

### The durable fix works

`3fb0111` — `workspace-up` now reads each omp pane's live log and compares it with the config:

```
omp wD:p9    .dotfiles        pid 20944  STALE: contextWindow 0: never compacts (config 500000)
omp wG:p1    thor-voiceai     pid 84434  ok: no turn logged yet, started after the config
omp wG:p6    ai-assisted-dev  pid 80155  STALE: threshold 660000 vs config 500000
omp wG:pC    knowledge-graph  pid 4499   ok: window 1000000, threshold 500000
workspace: ... 2 omp stale, 3 need you - ... restart its omp (/exit, then ctrl+a in the pane)
```

It names the pane, says *why*, and gives the remedy — and it correctly distinguishes "no turn
logged yet, started after the config" from genuinely stale, which is the mistake a naive
mtime check would make.

Confirmed by the worker: prescient, bro and thor were restarted and all now log 1M / 500000.

### Still stale, by design of the report

| pane | why |
|---|---|
| **`wD:p9` (this session)** | up 6 days, `contextWindow 0` — my own pane. Cannot restart itself from inside. |
| `wG:p6` (ai-assisted-dev) | up 6 days, threshold 660000 — a project that is not mine to restart |

### FALSE POSITIVE: the Discord "unhealthy"

The summary also said:

```
discord: gateway: the running bot never logged `bot ready` since it started
```

**That is wrong.** The bot is connected and working:

- **33** `bot ready` lines in `bridge.log`
- one live TCP connection to the gateway (`lsof` → 1 TCP)
- notifications flowing a minute before the check: `[17:42:56] notified #dotfiles-wD: idle (wD:pJ, …)`

The check looks for a `bot ready` line **after the process start time**, and the running bot
started Nov 12 — before the current log and before that check existed. So it reports "never" for
a bot that is demonstrably fine.

**Fix:** the check should accept *either* a ready line newer than the process start *or* evidence
of live operation (a `notified` line within the last few minutes, or an established TCP
connection). A health check that cries wolf on a healthy service trains the owner to ignore the
summary — which is worse than not checking.
