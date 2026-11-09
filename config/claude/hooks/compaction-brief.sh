#!/usr/bin/env bash
# PreCompact hook: stdout is appended to Claude Code's compact instructions
# (exit 0), for manual and auto compaction alike. Prints the owner's handoff
# brief, the one source shared with omp's omp-compaction-brief extension.
# Fail-open: no file, nothing printed, compaction proceeds as before.
cat "$HOME/.dotfiles/config/agents/compaction-brief.md" 2>/dev/null
exit 0
