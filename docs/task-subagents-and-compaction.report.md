# Report: sub-agents and proactive compaction (tk-09e43448c80b, tk-13ee9d2f08f9)

Task: `docs/task-subagents-and-compaction.md`. Two local commits, not pushed, in the doc's order of work. The mechanism was established first, then the brief, then the sub-agent rule.

| Commit | Task | What |
|---|---|---|
| `281a12f` | tk-13ee9d2f08f9 (compaction) | brief, hooks, thresholds, check script |
| the commit after `281a12f` | tk-09e43448c80b (sub-agents) | the rule in both context files, plus this report |

## To make it live

1. **Link the new omp extension** (setup.sh has the line): `ln -sf ~/.dotfiles/config/omp/extensions/omp-compaction-brief.ts ~/.omp/agent/extensions/omp-compaction-brief.ts`. Everything else is already live through existing symlinks: `CLAUDE.md`, `settings.json`, `APPEND_SYSTEM.md`, `config.yml`.
2. **Start new sessions.** Context files and the thresholds are read at session start.
3. **Check:** `python3 scripts/check-compaction-brief.py` lists what a new session loads. Today everything shows "loaded" except that one extension link.

## Acceptance 2: does omp expose a compaction threshold or hook? Yes, both

**The doc's premise is half right.** `config/omp/config.yml` had no compaction key, and `statusLine: preset: compact` is indeed the status line. But **omp itself reads compaction settings**; our config simply never set them. Sources, all in the installed `@oh-my-pi/pi-coding-agent` 17.3.4 (`omp --version` → `omp/17.3.4`) and its `@oh-my-pi/pi-agent-core`:

- **The threshold** is set in `src/config/settings-schema.ts:2202`. The `compaction.thresholdPercent` setting defaults to `-1`, which means legacy reserve-based, i.e. near full. Its UI options run 10–95%. `compaction.thresholdTokens` overrides the percentage if set.
  - It is applied in `pi-agent-core/src/compaction/compaction.ts:360` (`resolveThresholdTokens`) for **every** strategy.
  - Nested YAML maps to these dotted keys (`settings.ts:108` splits each path on "."; `statusLine: preset:` works the same way). So `compaction: thresholdPercent: 66` in config.yml is read.
- **The strategy** is set in `settings-schema.ts:2166`: `compaction.strategy` is one of `context-full | handoff | shake | snapcompact | off`. The default is **`snapcompact`**, which archives history as images and **makes no LLM call, so it writes no summary.**
- **The hook:** `src/extensibility/shared-events.ts:77/384` defines the `session.compacting` extension event. Its handler may return `context: string[]` (extra lines) or `prompt` (a full override).
  - It is emitted in `src/session/session-maintenance.ts:1638`, on the LLM-summary path (`needsLlm`).
  - The lines are appended to the summarizer prompt in `pi-agent-core/.../compaction.ts:895` (`formatAdditionalContext`).
  - There is also `session_before_compact`, which can cancel or replace a compaction.
- **No env var** for the threshold in omp; the setting is the mechanism.

**For Claude Code** (2.1.319, `claude --version`; strings read from the installed binary):
- `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is an env var the binary reads (listed among its env vars, and named in its autocompact logs).
- The summarizer prompt says to follow summarization instructions found in the context. Its own example is a `## Compact Instructions` section, which is why the brief carries that heading.
- The `PreCompact` hook (matcher `manual`/`auto`): exit 0 means "stdout appended as custom compact instructions"; exit 2 blocks compaction.

**So no key was invented.** Every key and hook used here is one the installed tool reads. The check script confirms the threshold key is in omp's own settings schema.

## What was done, per idea

### Idea 2: compaction (commit `281a12f`)

- **The brief, one source:** `config/agents/compaction-brief.md`, the owner's five items word for word under `## Compact Instructions`. It reaches the summarizer by **three routes**:
  - omp: the new extension `config/omp/extensions/omp-compaction-brief.ts` returns it from `session.compacting` as `context`;
  - Claude: `config/claude/hooks/compaction-brief.sh`, wired as `PreCompact` in `settings.json`, prints it;
  - both context files carry it verbatim (`CLAUDE.md` and `APPEND_SYSTEM.md`, "Compaction: a handoff brief, early").
- **When:** the context-file sections give the doc's rule: about two thirds, at a natural boundary (after a verified unit, before a dispatch, at a checkpoint), never mid-step. Run `/compact` yourself at the next boundary once past about half.
- **Thresholds (step 4, now that the mechanism is known):**
  - omp: `compaction.thresholdPercent: 66` in `config.yml`, committed alone. The owner's uncommitted `modelRoles.task` change is still uncommitted.
  - Claude: `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=66` in `settings.json` `env`.

### Idea 1: sub-agents (the second commit)

- omp, in `APPEND_SYSTEM.md` "Delegation rules": a new **Atomic context (sub-agents)** bullet.
- Claude, in `CLAUDE.md`: a new **Sub-agents for atomic context** section, pointing at the omp rule as the same rule.
- Shared clauses:
  - multi-file, multi-step and, above all, read-heavy work goes to a sub-agent with a self-contained brief;
  - it returns a **compressed result** (what changed with paths, what was verified, what is open), **never its working narrative or file dumps**;
  - verify its claims before reporting;
  - a sub-agent does not delegate further.
- For Claude, the existing "stay inline for a handful of tool calls" sense is kept, so the rule doesn't fight Claude Code's own cost guidance.

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | The brief (five items, near-verbatim) is in the context files, and a check shows it is loaded | PASS. See the check output below. |
| 2 | A written answer, with sources, on omp's threshold and hook | PASS. See the section above: yes, `compaction.thresholdPercent` and `session.compacting`. |
| 3 | The sub-agent rule exists for both, and they don't contradict | PASS. Same clauses in both. Claude's section names the omp rule as its twin; omp's points back to "Your role" for the no-further-delegation rule. |
| 4 | No config key that nothing reads | PASS. `compaction.thresholdPercent` is in omp's schema and applied in `resolveThresholdTokens`; the check script verifies the schema key. |
| 5 | No change for a subagent told not to delegate | PASS. omp's "Your role" clause is untouched, and the new bullet defers to it. Claude's section ends "If you are a sub-agent, or were told not to delegate: do not spawn further." |

Output of `python3 scripts/check-compaction-brief.py`:

```
PASS config/agents/compaction-brief.md: five items
PASS config/claude/CLAUDE.md: the five items verbatim
PASS config/omp/context-files/APPEND_SYSTEM.md: the five items verbatim
PASS Claude PreCompact hook prints the brief (exit 0)
PASS omp extension: session.compacting returns the brief as summarizer context
PASS settings.json: PreCompact runs the hook
PASS settings.json: CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=66
PASS config.yml: compaction.thresholdPercent=66
PASS installed omp reads compaction.thresholdPercent (its settings schema has the key)

live (what a new session loads):
  loaded     ~/.claude/CLAUDE.md
  loaded     ~/.claude/settings.json
  loaded     ~/.omp/agent/APPEND_SYSTEM.md
  loaded     ~/.omp/agent/config.yml
  NOT LINKED ~/.omp/agent/extensions/omp-compaction-brief.ts  (run setup.sh)
OK
```

The extension check runs the real `.ts` under bun with a stand-in `api`, and asserts that the handler returns exactly the brief.

## For the owner: one decision

**omp's default strategy writes no summary,** so the brief only shapes omp compactions that ask an LLM:
- a manual `/compact`;
- the `context-full` and `handoff` strategies;
- snapcompact's fallback to the summarizer.

At 66%, **auto**-maintenance on omp will run snapcompact (archive to images), not a brief. If you want every omp compaction to be a handoff brief, set `compaction.strategy: context-full` (or `handoff`, which also starts a new session). That costs one summary LLM call per compaction. I left the strategy alone, because it changes behaviour on every omp pane. Claude has no such split: its auto and manual compactions both summarize, so both get the brief.

## Notes

- **A brief slip, fixed:** `config.yml` had no trailing newline, so the first append glued `# Context compaction…` onto `enabled: false`. That is the live, symlinked file. I fixed it within seconds and checked that both the working file and the staged copy parse with PyYAML. An omp started in that window would have read a broken config.
- I didn't create the extension symlink in `~/.omp` myself (writes stay inside the project). It is in `setup.sh`.
- **Not tested live:** Claude's actual use of `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=66`, by watching a session compact at 66%. That needs a session to fill up. The binary reads the variable; I didn't observe it firing.
