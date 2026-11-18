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
