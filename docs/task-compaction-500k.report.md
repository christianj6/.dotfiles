# REPORT: omp compaction at 500k — and why it does nothing on the default model yet

Spec: `docs/task-compaction-500k.md`.

## Headline

**`thresholdTokens: 500000` works on claude-sonnet-5 and is a no-op on both opencode-go
models — and so was the old `thresholdPercent: 66`.** omp does not know their context window
(runtime value 0), and with window 0 it skips auto-compaction entirely, whatever threshold is
set. The default role (deepseek-v4.1-flash) has never threshold-compacted: sessions have run
past 1M tokens and only compacted after the provider rejected the prompt. The fix is one
models.yml override, proposed below and **not shipped**, as the spec asked.

## The mechanism (omp 17.3.4, `cli.js`)

Every auto-compaction call site (post-agent-end, pre-prompt, mid-run) starts with:

```js
let o = model.contextWindow ?? 0; if (o <= 0) return false;
```

and the check itself (`xQ`) also returns false for `window <= 0`. Only after that does the
resolver (`QQ`) run: `thresholdTokens` first, clamped to `window - 1`; `thresholdPercent` only
when `thresholdTokens` is unset or `<= 0`.

So for an unknown window the question is not "how low does 500k clamp" but "nothing runs".

## Effective threshold per model

| model | role | window omp uses | effective threshold |
|---|---|---|---|
| `anthropic/claude-sonnet-5` | task | 1,000,000 | **500,000** — as asked |
| `opencode-go/deepseek-v4.1-flash` | default, advisor, commit | **0** (unknown) | **none — never auto-compacts** |
| `opencode-go/glm-5.3-flash` | smol, slow | **0** (unknown) | **none — never auto-compacts** |

Evidence (read-only; omp debug logs exist from 2026-11-09):

- **The model cache:** `~/.omp/agent/models.db` stores `"contextWindow":null` for both
  opencode-go models (`omp models` prints `-`).
- **deepseek-v4.1-flash:** all 391 logged threshold decisions have `contextWindow:0`,
  `thresholdTokens:0` and `shouldCompact:false`. Example from `~/.omp/logs/omp.2026-11-09.11848.log`,
  which I re-read myself:
  `"contextWindow":0,"strategy":"snapcompact","thresholdTokens":0,"assistantUsageContextTokens":943919,…,"shouldCompact":false`
- **deepseek's compactions in transcripts:** all five came at about 955k–1.05M tokens, and
  they were overflow recoveries (`400 … the prompt exceeds the model context`, then
  `Retry budget exhausted`) or manual. None was a threshold compaction.
- **glm-5.3-flash:** 3 logged decisions, all with window 0 and no compaction, at up to 364k
  tokens. It has never compacted.
- **Control:** sessions on Claude models log `contextWindow:1000000` with
  `thresholdTokens:660000` (the old 66%). The only three "Mid-run compaction ran" lines fired
  at 660k–662k on those sessions. The machinery works whenever the window is known.

## What shipped

`config/omp/config.yml`: `thresholdPercent: 66` → `thresholdTokens: 500000`, with a comment
covering the precedence, the clamp, and the window-0 skip. **`thresholdPercent` is removed,
not kept:** with a token value set it can never apply, and it would not rescue the
opencode-go models either, because window 0 stops both. No other key changed.

This is correct and needed for the Claude roles, but on its own it does **not** meet "omp
agents always auto compact around 500k": the default model is still uncovered.

## Proposed (not shipped): give omp the opencode-go windows

`config/omp/models.yml`. The schema accepts `providers.<p>.modelOverrides.<id>.contextWindow`,
and an override wins over the discovered value (`contextWindow: f.contextWindow ?? h.contextWindow`):

```yaml
providers:
  opencode-go:
    compat:
      promptCacheSessionHeader: x-opencode-session
    # omp discovers these with no context window (null -> 0), and omp never
    # auto-compacts a model with window 0. Values: the provider's own limit,
    # observed as the overflow point in transcripts (~1.048M).
    modelOverrides:
      deepseek-v4.1-flash:
        contextWindow: 1048576
      glm-5.3-flash:
        contextWindow: 1048576
```

Why these numbers:

- **deepseek-v4.1-flash:** the overflow point is measured. Contexts reached 1,048,4xx tokens
  before the provider's 400, and one turn ended with `stopReason: length` at 1,048,558. The
  openrouter catalog also lists the model at 1M.
- **glm-5.3-flash:** the number is **inferred, not measured** on opencode-go. Other catalogs
  list it at 1M, and its openrouter sessions compacted at up to 983k. If its real opencode-go
  window were below 500k, it would overflow before compacting, which is no worse than today.

Effect with the override, on all three models: compaction at 500,000.

Side effects to weigh:

- `contextWindow` also feeds omp's context display and budget maths for these models, and
  today those run on 0.
- Any other omp feature keyed on the window would start working for them; I did not audit
  each one.

**Decision needed:** ship the override (my recommendation), or accept that 500k applies to
the Claude roles only.

## Run

- Read-only investigation: `omp models`, the model cache, `~/.omp/logs/omp.*.log`, the
  session transcripts, and `cli.js`. The log and transcript sweep was done by a sub-agent;
  I re-checked its decisive log line myself.
- `git diff` touches only the `compaction:` block of `config/omp/config.yml`. The
  `modelRoles:` lines are untouched.

## Outside the spec

`config/claude/settings.json` has an uncommitted change that I did not make: the same keys
in a different order, with no values changed. I left it out of my commit.
