#!/bin/bash

# Script to set up OpenCode devcontainer in any project directory
# Usage: ./setup-opencode-devcontainer.sh [target-project-dir]

set -e

# Dotfiles directory is always at ~/.dotfiles
DOTFILES_DIR="$HOME/.dotfiles"

# Get target directory (default to current directory)
TARGET_DIR="${1:-.}"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"

echo "Setting up OpenCode devcontainer in: $TARGET_DIR"

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

# Create .opencode directory in target project
mkdir -p "$TARGET_DIR/.opencode"

# Copy devcontainer files from dotfiles repo
echo "Copying devcontainer configuration files..."
cp "$DOTFILES_DIR/.opencode/Dockerfile" "$TARGET_DIR/.opencode/"
cp "$DOTFILES_DIR/.opencode/devcontainer.json" "$TARGET_DIR/.opencode/"
cp "$DOTFILES_DIR/.opencode/init-firewall.sh" "$TARGET_DIR/.opencode/"
cp "$DOTFILES_DIR/.opencode/package.json" "$TARGET_DIR/.opencode/"

# Make init-firewall.sh executable
chmod +x "$TARGET_DIR/.opencode/init-firewall.sh"

echo "Devcontainer configuration copied successfully"
echo ""
echo "Starting devcontainer..."

# Change to target directory
cd "$TARGET_DIR"

# Start the devcontainer and get container ID
CONTAINER_ID=$(devcontainer up --config .opencode/devcontainer.json --workspace-folder  . --remove-existing-container | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)

if [ -z "$CONTAINER_ID" ]; then
    echo "Error: Failed to start devcontainer"
    exit 1
fi

echo "Devcontainer started with ID: $CONTAINER_ID"
echo ""

echo ""
echo "Setup complete!"
echo ""
echo "To connect to this devcontainer, run:"
echo "  opencode"
