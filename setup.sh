#!/bin/bash
set -euo pipefail

# Detect OS
if [[ "$(uname)" == "Darwin" ]]; then
    OS="macos"
elif [[ "$(uname)" == "Linux" ]]; then
    OS="linux"
else
    echo "Unsupported operating system"
    exit 1
fi

echo "Installing dependencies for $OS..."

# Install system packages
if [[ "$OS" == "linux" ]]; then
    sudo apt-get update
    sudo apt-get install -y curl wget git build-essential software-properties-common
    # Install neovim from PPA for latest version
    sudo add-apt-repository ppa:neovim-ppa/unstable -y
    sudo apt-get update
    sudo apt-get install -y neovim ripgrep bear ranger tmux

    # Install lazygit (skip if already on PATH)
    if ! command -v lazygit &> /dev/null; then
        LAZYGIT_TMP="$(mktemp -d)"
        LAZYGIT_VERSION=$(curl -s "https://api.github.com/repos/jesseduffield/lazygit/releases/latest" | grep -Po '"tag_name": "v\K[^"]*')
        curl -Lo "$LAZYGIT_TMP/lazygit.tar.gz" "https://github.com/jesseduffield/lazygit/releases/latest/download/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz"
        tar xf "$LAZYGIT_TMP/lazygit.tar.gz" -C "$LAZYGIT_TMP" lazygit
        sudo install "$LAZYGIT_TMP/lazygit" /usr/local/bin
        rm -rf "$LAZYGIT_TMP"
    fi

    # Install k9s (skip if already on PATH)
    if ! command -v k9s &> /dev/null; then
        if command -v brew &> /dev/null; then
            brew install derailed/k9s/k9s
        else
            curl -sS https://webinstall.dev/k9s | bash
        fi
    fi
elif [[ "$OS" == "macos" ]]; then
    # Install Homebrew if not installed
    if ! command -v brew &> /dev/null; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    # A fresh install doesn't put brew on PATH for this shell yet
    if ! command -v brew &> /dev/null; then
        if [[ -x /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -x /usr/local/bin/brew ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
    fi
    brew install neovim ripgrep lazygit derailed/k9s/k9s bear wget maccy ranger tmux
fi

# Install nvm and Node.js (skip installer if nvm is already present)
export NVM_DIR="$HOME/.nvm"
if [ ! -s "$NVM_DIR/nvm.sh" ]; then
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install 22
node -v
nvm current
npm -v

# Install devcontainers CLI
npm install -g @devcontainers/cli

# Install Miniconda (skip if already installed)
if [ ! -d "$HOME/miniconda3" ]; then
    if [[ "$OS" == "macos" ]]; then
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh"
    else
        MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    fi
    wget "$MINICONDA_URL" -O ~/miniconda.sh
    bash ~/miniconda.sh -b -p "$HOME/miniconda3"
    rm ~/miniconda.sh
fi

# Add conda to path for current session
export PATH="$HOME/miniconda3/bin:$PATH"

# Install aider
python -m pip install aider-install
aider-install

# Create config directories
mkdir -p ~/.config

# Create symlinks
ln -sf ~/.dotfiles/nvim ~/.config

# OS-specific symlinks
if [[ "$OS" == "macos" ]]; then
    ln -sf ~/.dotfiles/ghostty ~/.config
    mkdir -p ~/Library/"Application Support"/"Leader Key"
    ln -sf ~/.dotfiles/leaderkey/config.json ~/Library/"Application Support"/"Leader Key"/config.json
fi

# ~/.local/bin entrypoints for the devcontainer setup scripts, so nothing
# outside this repo needs to hardcode a scripts/ path.
mkdir -p ~/.local/bin
ln -sf ~/.dotfiles/scripts/devcontainers/setup-claude-devcontainer.sh ~/.local/bin/claude-setup
ln -sf ~/.dotfiles/scripts/devcontainers/setup-opencode-devcontainer.sh ~/.local/bin/opencode-setup

# Keep the devcontainer helper functions in ~/.zshrc current, without ever
# touching anything else you keep there.
sync_zshrc() {
    local zshrc="$HOME/.zshrc"
    local begin_marker="# >>> dotfiles devcontainer helpers >>>"
    local end_marker="# <<< dotfiles devcontainer helpers <<<"

    touch "$zshrc"

    # Drop legacy single-line aliases from before scripts/ was reorganized;
    # the managed block below and the ~/.local/bin symlinks above replace them.
    local work
    work="$(mktemp)"
    grep -vF \
        -e "alias claude-setup=\"~/.dotfiles/scripts/setup-claude-devcontainer.sh\"" \
        -e "alias opencode-setup=\"~/.dotfiles/scripts/setup-opencode-devcontainer.sh\"" \
        "$zshrc" > "$work" || true

    local block
    block="$(cat <<'BLOCK'
claude() {
    docker exec -it "$(devcontainer up --workspace-folder . | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)" claude
}

opencode() {
    devcontainer exec --config .opencode/devcontainer.json --workspace-folder . opencode
}
BLOCK
)"

    local begin_line end_line
    begin_line="$(grep -nF "$begin_marker" "$work" 2>/dev/null | head -1 | cut -d: -f1)" || true
    end_line="$(grep -nF "$end_marker" "$work" 2>/dev/null | head -1 | cut -d: -f1)" || true

    local final
    final="$(mktemp)"
    if [ -n "${begin_line:-}" ] && [ -n "${end_line:-}" ] && [ "$end_line" -gt "$begin_line" ]; then
        # Existing block: replace its contents in place, keep everything else untouched.
        { head -n "$begin_line" "$work"; printf '%s\n' "$block"; tail -n "+$end_line" "$work"; } > "$final"
    else
        # No block yet: append a fresh one at the end.
        { cat "$work"; echo ""; echo "$begin_marker"; printf '%s\n' "$block"; echo "$end_marker"; } > "$final"
    fi
    rm -f "$work"

    if cmp -s "$final" "$zshrc"; then
        rm -f "$final"
        return 0
    fi

    if command -v zsh &> /dev/null && ! zsh -n "$final" 2> /dev/null; then
        echo "Warning: generated ~/.zshrc failed a zsh syntax check; leaving your ~/.zshrc untouched." >&2
        rm -f "$final"
        return 0
    fi

    cp "$zshrc" "$zshrc.bak.$(date +%Y%m%d%H%M%S)"
    mv "$final" "$zshrc"
    echo "Updated $zshrc (previous version backed up alongside it)"
}
sync_zshrc

echo "Setup complete for $OS"
