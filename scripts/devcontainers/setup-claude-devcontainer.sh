#!/bin/bash

# Script to set up Claude Code devcontainer in any project directory
# Usage: ./setup-claude-devcontainer.sh [target-project-dir]

set -e

# Dotfiles directory is always at ~/.dotfiles
DOTFILES_DIR="$HOME/.dotfiles"

# Get target directory (default to current directory)
TARGET_DIR="${1:-.}"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

echo "Setting up Claude Code devcontainer in: $TARGET_DIR"

# Check if @devcontainers/cli is installed
if ! command -v devcontainer &> /dev/null; then
    echo "Error: @devcontainers/cli is not installed"
    echo "Please run: npm install -g @devcontainers/cli"
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "Error: Docker is not running"
    echo "Please start Docker and try again"
    exit 1
fi

# Create .devcontainer directory in target project
mkdir -p "$TARGET_DIR/.devcontainer"

# Copy devcontainer files from dotfiles repo
echo "Copying devcontainer configuration files..."
cp "$DOTFILES_DIR/.devcontainer/Dockerfile" "$TARGET_DIR/.devcontainer/"
cp "$DOTFILES_DIR/.devcontainer/devcontainer.json" "$TARGET_DIR/.devcontainer/"
cp "$DOTFILES_DIR/.devcontainer/init-firewall.sh" "$TARGET_DIR/.devcontainer/"

# Make init-firewall.sh executable
chmod +x "$TARGET_DIR/.devcontainer/init-firewall.sh"

echo "Devcontainer configuration copied successfully"
echo ""
echo "Starting devcontainer..."

# Change to target directory
cd "$TARGET_DIR"

# Start the devcontainer and get container ID
CONTAINER_ID=$(devcontainer up --workspace-folder . | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)

if [ -z "$CONTAINER_ID" ]; then
    echo "Error: Failed to start devcontainer"
    exit 1
fi

echo "Devcontainer started with ID: $CONTAINER_ID"
echo ""
echo "Connecting to devcontainer as 'claude' user..."
echo ""

# Connect to the container as claude user
docker exec -it "$CONTAINER_ID" claude

echo ""
echo "Setup complete!"
echo ""
echo "To reconnect to this devcontainer later, run:"
echo "  claude"
