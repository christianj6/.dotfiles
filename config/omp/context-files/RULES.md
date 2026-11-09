# Global rules

- The coordinator researches nothing in bulk: codebase reading and research go to claude or a subagent. Whoever does research never spends more than 3 consecutive turns on it without producing an artifact.
- Delegate implementation packages to claude in this project, or to @task subagents (cheaper model), with directive specs: exact paths, signatures, test cases.
- Never run a nested agent CLI inside your own herdr pane without stripping HERDR_* env vars.
