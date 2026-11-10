# Report: make sub-agents the default (docs/task-make-subagents-default.md)

Committed locally, not pushed. No hook built.

## Files changed

- `config/omp/context-files/APPEND_SYSTEM.md`: the "Atomic context" bullet rewritten as a trigger, plus the ratio paragraph in its copy of the brief;
- `config/claude/CLAUDE.md`: "Sub-agents for atomic context" rewritten the same way, plus the same brief paragraph;
- `config/agents/compaction-brief.md`: the ratio paragraph;
- `scripts/check-delegation.py`: new;
- this report.

**Live at the next session start:** both context files are already symlinked. The brief reaches omp through the extension and claude through the `PreCompact` hook, which both read the file.

## 1. The trigger, in both files

The prose was replaced, not added to. Both sections now read the same way:
- **The trigger:** "More than ~3 reads/searches to answer one question → stop and dispatch it … If your first instinct is 'I'll just read these files', that is the trigger."
- **The exception:** "a small lookup whose target you know (1-3 calls) stays inline. This is a threshold, not a ban."
- **The brief:** a fill-in block with `GOAL / WHERE / RULED OUT / RETURN`. RETURN is the compressed result: exact paths, what was verified, what is open, no narrative and no file dumps.
- **End-of-turn self-check:** a turn with more than 5 inline reads and no sub-agent says why in its report, and the checker command is named.

omp's subagent exemption ("a spawned subagent does not delegate further") is kept. So is claude's "If you are a sub-agent … do not spawn further".

**Prefer/consider:** the delegation sections hold no "prefer" or "consider", and none were there before this change either. So the soft-word theory explains nothing, and the threshold is what changed. This is enforced: `check-delegation.py --rules` fails on either word in those sections, or if any part of the trigger or brief goes missing. A mutation test (adding "prefer subagents" to a temp copy) fails as it must.

## 2. The checker: `scripts/check-delegation.py`

```
python3 scripts/check-delegation.py <transcript.jsonl> | --omp [repo] | --claude [repo]   [--strict]
python3 scripts/check-delegation.py --rules | --selftest
```

- **It reads** omp (`toolCall`) and claude (`tool_use`) transcripts and counts the parent session's calls. A subagent's own calls are in its own transcript.
- **Categories:** subagent (`task` / `Task` / `Agent`), edit/write, reads (read/grep/glob tools and read-like bash: `cat`, `sed -n`, `grep`, `rg`, `ls`, `find`, `head`, `tail`, `wc`, `jq`, `git show/log/diff/status`), and other bash.
- **Ratio** = dispatches / (bash + reads + edit/write + dispatches). This is the spec's formula: 2 / (2103 + 206 + 2) = 0.1%.
- **Over-threshold turns** are turns with more than 5 inline reads and no subagent. `--strict` exits 1 below target.

**Checked against known sessions:**
- **omp:** raw tool-name counts in the coordinator's transcript are bash 1876, read 69, grep 2, glob 1, edit 68, write 68, task 1. The checker prints 1948 bash+reads, 136 edit/write and 1 task, an exact match.
- **claude:** the raw count is 728 `tool_use` blocks, but 102 of them are re-written copies under the same `tool_use` id. The checker de-duplicates by id, leaving 626 unique calls: 564 bash+reads, 63 edit/write, and 6 others (TaskStop, ToolSearch, Skill). A naive grep overcounts claude by about 16%.
- **`--selftest`** covers both formats, the dedupe, read-like bash and an over-threshold turn.

**Your 2103 vs. my 1948:** your "2103 bash" likely counted more than the parent's calls, for example `toolName: "bash"` in the tool results as well. The checker counts tool-call blocks only.

## 3. The compaction brief

`config/agents/compaction-brief.md` now ends: *"Then restate the delegation ratio, so every compaction re-states it: more than ~3 reads/searches to answer one question goes to a sub-agent. State this session's sub-agent dispatches against its inline tool calls as far as the conversation shows them (target: dispatches >= 5% of tool calls, and no turn with more than 5 inline reads and no sub-agent), and say to run `check-delegation.py` … after compaction for the exact ratio."*

The summarizer has no tools, so it states what the conversation shows, and the exact number comes from the script after compaction. Both context-file copies carry the paragraph. `check-compaction-brief.py` and `check-coordinator-role.py` (including `--selftest`) still pass.

## 4. Can omp's `tool_call` hook inject context? No. It can only block or rewrite the input

Source: the installed `@oh-my-pi/pi-coding-agent`, `src/extensibility/`.
- **`shared-events.ts`, `ToolCallEventResult`:** the only fields are `block`, `reason` ("returned to LLM as error") and `input` (replacement arguments). There is no context field.
- **`extensions/wrapper.ts`:** `block` throws `reason` as the tool's error, and `input` replaces the arguments. Nothing else is read.
- **`extensions/runner.ts` `emitToolCall`:** the first `block` wins, and otherwise the last result is used.

So the spec's "allow the call but append a line" cannot be done from `tool_call`. A `block` with a reason is the only message it can send, and that refuses the read.

**Two other hooks can do what was wanted, without blocking:**
- **`tool_result`** (`types.ts:1245`, `ToolResultEventResult`): its handler may return replacement `content`. A counter in `tool_call` plus a `tool_result` handler could pass the 4th inline read through and **append the nudge line to that read's result**. The model sees it right after the read, the same shape as the `avoid_claim` retry line.
- **`pi.sendMessage(msg, { deliverAs: "steer" | "nextTurn" })`** (`types.ts:1317`) adds a custom message to the session, either mid-turn or on the next turn.

Not built: that is your call (spec item 3). If wanted, the shape is a `tool_call` counter plus a `tool_result` append.

## 5. Before, and what "good" is

The baseline, run today:

| session | bash+reads (read-like) | edit/write | task | ratio | turns | over-threshold turns |
|---|---|---|---|---|---|---|
| omp coordinator (wD:p9) | 1948 (770) | 136 | 1 | **0.0%** | 223 | **43** |
| claude workhorse (this one) | 564 (198) | 63 | 0 | **0.0%** | 64 | **10** |

**Good** (the checker's `TARGET`, and what both files now name):
- **Delegation ratio ≥ 5%,** about one dispatch per 20 parent calls. A turn that does one exploration should show it: roughly one dispatch to a dozen parent calls of dispatch, verify and edit.
- **0 over-threshold turns,** or each one explained in that turn's report.

At those targets, the coordinator's 2085 calls would carry about 100 dispatches, not 1, and the 43 read-heavy turns would each have handed their reading off.

**This turn, by its own rule:** it had more than 5 inline reads and no subagent. Reading omp's extension source for item 4 took about 6 calls across `shared-events.ts`, `wrapper.ts`, `runner.ts` and `types.ts`. Under the new trigger that was a dispatch. I kept it inline because the rule did not exist yet when the turn started. It is counted in the 10 above.

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | Both files carry the threshold and the brief as a trigger; no prefer/consider in the section | PASS. `check-delegation.py --rules` |
| 2 | The ratio checker exists and is checked against a known session | PASS. omp matches the raw counts exactly; claude's raw count has 102 duplicates, which the checker removes |
| 3 | The ratio is in the compaction brief | PASS. In the brief and both copies |
| 4 | Can `tool_call` inject context, with sources; no hook built | PASS. Block or rewrite only; `tool_result` can append. No hook built |
| 5 | Before/after and what "good" looks like | PASS. See the table: 0.0% / 43 and 0.0% / 10 against ≥ 5% / 0 |
| 6 | Inline work for a small, known lookup is allowed | PASS. "stays inline. This is a threshold, not a ban" in both files |
