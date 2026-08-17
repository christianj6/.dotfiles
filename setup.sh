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

echo "Setup complete for $OS"
