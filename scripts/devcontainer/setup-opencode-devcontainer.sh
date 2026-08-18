#!/bin/bash

# Sets up the OpenCode devcontainer template in any project directory.
# Usage: ./setup-opencode-devcontainer.sh [target-project-dir]
#
# Shared provisioning logic lives in lib.sh — see there for what this
# shares with setup-claude-devcontainer.sh and what's deliberately kept
# separate.

set -e

source "$HOME/.dotfiles/scripts/devcontainer/lib.sh"

TARGET_DIR="$(resolve_target_dir "${1:-.}")"
echo "Setting up OpenCode devcontainer in: $TARGET_DIR"

check_devcontainer_prerequisites
copy_devcontainer_template opencode "$TARGET_DIR" Dockerfile devcontainer.json init-firewall.sh package.json

# Force-recreate the container on every re-run, unlike claude-setup: this
# script never attaches you to it (the `opencode` shell helper in setup.sh
# does that afterward), so re-running it is how you pick up template/
# Dockerfile changes. --remove-existing-container guarantees you land on a
# container matching what was just copied, instead of one reused via
# devcontainer's own config-hash cache.
start_devcontainer_template opencode "$TARGET_DIR" --remove-existing-container

echo ""
echo "Setup complete!"
echo ""
echo "To connect to this devcontainer, run:"
echo "  opencode"
