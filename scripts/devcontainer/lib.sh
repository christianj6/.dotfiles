#!/bin/bash
# Shared plumbing for the claude-setup / opencode-setup installers
# (setup-claude-devcontainer.sh / setup-opencode-devcontainer.sh). Each
# installer sources this file, then calls these functions with its own
# agent name and connection behavior — everything that isn't genuinely
# agent-specific (prerequisite checks, copying the template, starting the
# container) lives here exactly once.
#
# The installers intentionally still differ in:
#   - which files ship (opencode also ships package.json)
#   - whether `devcontainer up` force-recreates the container
#     (--remove-existing-container) — documented at each call site
#   - how you land in the container afterward (claude execs in immediately;
#     opencode just provisions, since the `opencode` shell helper — see
#     setup.sh — handles reconnecting)

# Dotfiles directory is always at ~/.dotfiles.
DOTFILES_DIR="$HOME/.dotfiles"

# resolve_target_dir <path> -> absolute path (defaults to cwd)
resolve_target_dir() {
    local dir="${1:-.}"
    (cd "$dir" && pwd)
}

# check_devcontainer_prerequisites -> exits 1 with guidance if unmet
check_devcontainer_prerequisites() {
    if ! command -v devcontainer &> /dev/null; then
        echo "Error: @devcontainers/cli is not installed"
        echo "Please run: npm install -g @devcontainers/cli"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        echo "Error: Docker is not running"
        echo "Please start Docker and try again"
        exit 1
    fi
}

# copy_devcontainer_template <agent> <target-dir> <file...>
# Copies the named template files from .devcontainer/<agent>/ (in this
# dotfiles repo) into <target-dir>/.devcontainer/<agent>/ and makes
# init-firewall.sh executable.
copy_devcontainer_template() {
    local agent="$1" target_dir="$2"
    shift 2

    local src_dir="$DOTFILES_DIR/.devcontainer/$agent"
    local dest_dir="$target_dir/.devcontainer/$agent"

    mkdir -p "$dest_dir"

    echo "Copying devcontainer configuration files..."
    local file
    for file in "$@"; do
        cp "$src_dir/$file" "$dest_dir/"
    done
    chmod +x "$dest_dir/init-firewall.sh"
    echo "Devcontainer configuration copied successfully"
}

# start_devcontainer_template <agent> <target-dir> [extra devcontainer-up args...]
# Runs `devcontainer up` against .devcontainer/<agent>/devcontainer.json in
# target-dir and sets CONTAINER_ID. Exits 1 if the container fails to start.
start_devcontainer_template() {
    local agent="$1" target_dir="$2"
    shift 2

    echo ""
    echo "Starting devcontainer..."

    cd "$target_dir"
    CONTAINER_ID=$(devcontainer up --config ".devcontainer/$agent/devcontainer.json" --workspace-folder . "$@" \
        | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)

    if [ -z "$CONTAINER_ID" ]; then
        echo "Error: Failed to start devcontainer"
        exit 1
    fi

    echo "Devcontainer started with ID: $CONTAINER_ID"
}
