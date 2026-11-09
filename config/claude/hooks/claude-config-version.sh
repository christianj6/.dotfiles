#!/bin/sh
# SessionStart hook: publishes the harness config version per claude PROCESS,
# the counterpart of omp's omp-config-version.ts. Writes
# /tmp/claude-config-versions/<claude pid> containing config/omp/VERSION (one
# number for the whole harness, so omp and claude panes read the same scale).
# The claude-name herdr plugin reads it to name the pane claude-v<N>-<pane>,
# and workspace-rollout --list reads it for the version column.
#
# SessionStart fires on startup and resume, but also on /clear and compaction
# inside the same process. The marker is created only if absent, so it holds
# the version the PROCESS started with: a pane started at v36 keeps v36 after
# a bump until it is restarted, exactly like omp's marker.
# The claude pid is the nearest ancestor whose command is claude (the hook
# runs as claude -> shell -> this script). Prints nothing: SessionStart stdout
# would be added to the model's context. Fails silently.
v="$(tr -dc '0-9' < "$HOME/.dotfiles/config/omp/VERSION" 2>/dev/null)"
[ -n "$v" ] || exit 0
p=$$
i=0
while [ "$p" -gt 1 ] && [ $i -lt 12 ]; do
    comm="$(ps -o comm= -p "$p" 2>/dev/null)"
    case "${comm##*/}" in
        claude) break ;;
    esac
    p="$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')"
    [ -n "$p" ] || exit 0
    i=$((i + 1))
done
case "$(ps -o comm= -p "$p" 2>/dev/null)" in
    *claude) ;;
    *) exit 0 ;;
esac
dir="${CLAUDE_CONFIG_MARKERS:-/tmp/claude-config-versions}"   # override: tests only
mkdir -p "$dir" 2>/dev/null
[ -e "$dir/$p" ] || printf '%s\n' "$v" > "$dir/$p" 2>/dev/null
exit 0
