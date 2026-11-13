# Compaction at 500k: verified, and one action left

Owner: *"update the config of omp so that omp agents always auto compact around 500k tokens."*

## Shipped

```
config/omp/config.yml
  compaction:
    thresholdTokens: 500000        # replaces thresholdPercent: 66

config/omp/models.yml
  providers.opencode-go.modelOverrides
    deepseek-v4.1-flash.contextWindow: 1000000
    glm-5.3-flash.contextWindow:    1000000
```

Two commits: `a4308aa` (the threshold), `7ce1a54` (the windows, key `modelOverrides.<id>.contextWindow`
from `models-config-schema.d.ts`).

## What I verified myself

**The override is being read.** `omp models`, fresh process:

```
deepseek-v4.1-flash    1M     (was "-")
glm-5.3-flash          1M     (was "-")
```

So the resolver now computes `Math.min(1000000 - 1, 500000)` = **500000** on those models,
where before the window was 0 and the guard `if (window <= 0) return false` skipped compaction
entirely.

## The bug this uncovered, which is the real find

**Auto-compaction has never run on the `default` role — not with the old 66%, and not since.**
With `contextWindow: null` in omp's cache, the guard returns false *before* the threshold is
consulted, so no percentage or token value could ever have applied.

Evidence (from the worker's read-only audit, and the guard in `cli.js` I checked myself):

- **391** logged decisions on deepseek, every one `contextWindow:0, thresholdTokens:0, shouldCompact:false`
- deepseek's five compactions came at **955k–1.05M**, all overflow recoveries after the provider
  rejected the prompt — never a threshold compaction
- **control**: Claude sessions logged `contextWindow:1000000, thresholdTokens:660000`, and the
  only three "Mid-run compaction ran" lines fired at 660k–662k

So the 66% was decorative on the model used most. That is the third setting today that looked
active and was not (`VERSION` at 35 across 52 commits; the empty `DISCORD_BOT_TOKEN=` shadowing
a real one; now 66%).

## The one action left

**Running omp panes must restart to pick this up.** They read the model cache and config at
process start; the logs still show `contextWindow:0, thresholdTokens:0` from processes that
began before `7ce1a54`. Verified: the live log lines are 0/0, while a *fresh* `omp models`
reports 1M.

That is the same "shipped but not live" omission as the lifeview daemon and the Discord bot —
and it is now the third instance, which is the argument for `workspace-up` covering omp panes
too. It does not today.

## Residual worth knowing

`claude-sonnet-5` (the `task` role) already had a real 1M window, so it was the only model
compacting at all — at 66%, i.e. 660k. With `thresholdTokens: 500000` it now compacts earlier,
at 500k, which is what the owner asked for. **No model compacts later than before.**
