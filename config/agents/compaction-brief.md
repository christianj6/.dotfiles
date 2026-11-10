## Compact Instructions

Write a handoff brief for the remaining work, not a history. Include:
1. The original task, near-verbatim.
2. Current step and the immediate next action.
3. Remaining plan in order, and the "done" criteria.
4. Changed files with exact paths and whether each change is verified.
5. Failed approaches not to repeat.

Then restate the role chain, so it survives this compaction: the omp coordinator decides, writes the spec, dispatches and verifies, and never edits a repo file itself (that is a process defect); claude and its subagents read, research and write code. Name which role this session holds.

Then restate the delegation ratio, so every compaction re-states it: more than ~3 reads/searches to answer one question goes to a sub-agent. State this session's sub-agent dispatches against its inline tool calls as far as the conversation shows them (target: dispatches >= 5% of tool calls, and no turn with more than 5 inline reads and no sub-agent), and say to run `python3 ~/.dotfiles/scripts/check-delegation.py --omp` (or `--claude`) after compaction for the exact ratio.
