#!/bin/bash

# Sets up the Claude Code devcontainer template in any project directory.
# Usage: ./setup-claude-devcontainer.sh [target-project-dir]
#
# Shared provisioning logic lives in lib.sh — see there for what this
# shares with setup-opencode-devcontainer.sh and what's deliberately kept
# separate.

set -e

source "$HOME/.dotfiles/scripts/devcontainer/lib.sh"

TARGET_DIR="$(resolve_target_dir "${1:-.}")"
echo "Setting up Claude Code devcontainer in: $TARGET_DIR"

check_devcontainer_prerequisites
copy_devcontainer_template claude "$TARGET_DIR" Dockerfile devcontainer.json init-firewall.sh

# Reuse the existing container across re-runs: `devcontainer up` only
# rebuilds when the Dockerfile/devcontainer.json content actually changed,
# and this script attaches you to the result immediately below, so you want
# continuity with whatever was already running, not a wipe on every re-run.
start_devcontainer_template claude "$TARGET_DIR"

echo ""
echo "Connecting to devcontainer as 'claude' user..."
echo ""
docker exec -it "$CONTAINER_ID" claude

echo ""
echo "Setup complete!"
echo ""
echo "To reconnect to this devcontainer later, run:"
echo "  claude"
