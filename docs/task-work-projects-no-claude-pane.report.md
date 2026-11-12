# REPORT: work projects get no claude pane; the split line gets HERDR_NO_NVIM=1

Spec: `docs/task-work-projects-no-claude-pane.md`.

## Changes

| file | change |
|---|---|
| `config/omp/context-files/APPEND_SYSTEM.md` "Startup: the claude workhorse pane" | work-project exception with the reason and date; delegation there is `@task` only; "the claude pane"/"the workhorse" elsewhere reads `@task` in a work project. Step 1 now `… --no-focus --env HERDR_NO_NVIM=1`, with why (`exec nvim` → not a shell → `agent_pane_busy`). |
| `config/herdr/skills/herdr-workstreams/SKILL.md` | the "quick side shell" split line gets `--env HERDR_NO_NVIM=1` + reason; the Subagents section opens with the work-project rule; step 1 names the `--cwd "$PWD" --env HERDR_NO_NVIM=1` alternative. |
| `config/claude/CLAUDE.md` | "A work project has no claude workhorse", so a claude there does not assume a handoff or ask to be restored. |
| `config/herdr/plugins/workspace-restore/restore.py` | never creates/starts/replaces a claude pane when the tab's cwd is under the work tree (`WORK_MARKER`, the same bare marker the omp scope extensions use); unit-tested, and live: `wG:t1 claude work project: no claude pane, by owner rule`. |

## The grep (acceptance 3)

    grep -rn -i 'pane split\|agent start\|claude pane\|workhorse' \
      config/omp/context-files config/claude config/agents config/omp/skills config/herdr/skills AGENTS.md

Instructions that open a pane: only `APPEND_SYSTEM.md:37-39` (startup step) and
`herdr-workstreams/SKILL.md` (lines 43, 70 + the subagent recipe) — both scoped above. The
other hits describe roles, handoff and messaging for a pane that already exists
(`APPEND_SYSTEM.md` 44-135, `AGENTS.md`, `peer.py`); they open nothing and are covered by the
one sentence added to the startup step. No `rule://` file or `config/claude/` file opens a pane.

## Not done

- Personal-project behaviour is unchanged apart from the corrected split line.
- Running omp sessions keep their old system prompt until they restart; thor's coordinator
  sees the new text from its next session.
