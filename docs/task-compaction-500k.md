# TASK: omp agents auto-compact at ~500k tokens of context

Owner: *"update the config of omp so that omp agents always auto compact around 500k tokens of
context."*

## What exists now

`config/omp/config.yml`:

```yaml
compaction:
  thresholdPercent: 66
```

## The setting that does what he asked

omp's schema (`@oh-my-pi/pi-coding-agent@17.3.4`, `settings-schema.d.ts`) has **both** keys:

```
compaction.thresholdTokens    number, default -1   "Compaction Token Limit"
compaction.thresholdPercent   number, default -1
compaction.strategy           enum ["context-full","handoff","shake","snapcompact","off"], default "snapcompact"
```

And the resolution order is **tokens first, percent as fallback** (`cli.js`, `QQ`):

```js
let h = n.thresholdTokens;
if (typeof h === "number" && Number.isFinite(h) && h > 0)
    return Math.min(i - 1, Math.max(1, h));       // i = context window
let f = n.thresholdPercent;
...
```

So adding `thresholdTokens: 500000` **takes precedence over the existing 66%** — no need to
remove the percent, but leaving both is a trap for the next reader: it looks like a 66%
threshold and silently is not. Set the one we mean and say why.

## The clamp, which is the part that needs a decision

`Math.min(contextWindow - 1, 500000)` means on a model whose window is **smaller than 500k**,
the effective threshold is just under the window — i.e. compact at the very end, which is the
opposite of "compact early". Measured windows:

| model (from `omp models`) | context |
|---|---|
| `claude-sonnet-5` (the `task` role) | **1M** |
| `deepseek-v4.1-flash` (`default`, `advisor`, `commit`) | **`-` — unknown to omp** |
| `glm-5.3-flash` (`smol`, `slow`) | **`-` — unknown** |

Two consequences:

1. On the **1M** model, 500k is a real, early threshold — exactly what the owner asked for.
2. On the three **unknown-window** models, `i` is whatever omp assumes when the window is not
   known. `Math.min(i-1, 500000)` then either behaves correctly (if `i` defaults high) or
   clamps to nearly the whole window (if `i` defaults low). **Find out which, and state it** —
   this is the difference between the setting working and it looking set while doing nothing.

If the unknown case is wrong, the honest fix is per-role: `thresholdTokens` cannot vary by
role in one config (it is global), so either
- accept 500k globally and document that the unknown-window models clamp, or
- use `thresholdPercent` where it is the better tool and note the tradeoff.

**Do not set a value that silently does nothing on the models we actually run.** The `default`
role is `deepseek-v4.1-flash` — the one used most — and its window is unknown.

## Change

```yaml
compaction:
  # Compact at ~500k tokens, not a percentage (owner, 2026-11-12). The resolver
  # tries thresholdTokens first and falls back to thresholdPercent, so the
  # percent below would be dead code -- set one, and this is the one we mean.
  thresholdTokens: 500000
```

Remove `thresholdPercent: 66` unless it is deliberately kept as the fallback for models where
500k exceeds the window — **if you keep it, say exactly that in a comment**, because otherwise
it reads as the active setting.

## Acceptance

1. `config/omp/config.yml` sets `compaction.thresholdTokens: 500000`.
2. The report states **what the effective threshold is** for each of the three models we run:
   `claude-sonnet-5` (1M window), `deepseek-v4.1-flash` and `glm-5.3-flash` (unknown window).
   That is the whole point of this task — a threshold that clamps to the window is not the
   owner's request.
3. If the unknown-window models clamp badly, say so plainly and propose the alternative rather
   than shipping a no-op.
4. Any `thresholdPercent` left in the file carries a comment saying when it applies.
5. No other config key changes.
