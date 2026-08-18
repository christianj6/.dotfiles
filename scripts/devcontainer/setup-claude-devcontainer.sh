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

# Force-recreate the container on every run, same as opencode-setup: a
# container reused for months accumulates a stale Docker Desktop VirtioFS
# bind-mount cache (files untouched since before the last recreation start
# throwing EPERM on read, `.git/packed-refs` included, breaking most git
# commands) - reproduced and root-caused 2026-08-18 against thor-voiceai's
# devcontainer, which had been alive since 2026-06-16. The few seconds of
# extra latency (fresh postStartCommand firewall init) is worth never
# hitting that again.
start_devcontainer_template claude "$TARGET_DIR" --remove-existing-container

echo ""
echo "Connecting to devcontainer as 'claude' user..."
echo ""
docker exec -it "$CONTAINER_ID" claude

echo ""
echo "Setup complete!"
echo ""
echo "To reconnect to this devcontainer later, run:"
echo "  claude"
