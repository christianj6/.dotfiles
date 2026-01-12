#!/bin/bash

# Detect OS
if [[ "$(uname)" == "Darwin" ]]; then
    OS="macos"
elif [[ "$(uname)" == "Linux" ]]; then
    OS="linux"
    # Check if running in WSL
    if [[ -f /proc/version ]] && grep -qi microsoft /proc/version; then
        IS_WSL=true
    fi
else
    echo "Unsupported operating system"
    exit 1
fi

echo "Installing dependencies for $OS..."

# Install system packages
if [[ "$OS" == "linux" ]]; then
    sudo apt-get update
    sudo apt-get install -y curl wget git build-essential
    # Install neovim from PPA for latest version
    sudo add-apt-repository ppa:neovim-ppa/unstable -y
    sudo apt-get update
    sudo apt-get install -y neovim ripgrep bear ranger tmux
    # Install lazygit
    LAZYGIT_VERSION=$(curl -s "https://api.github.com/repos/jesseduffield/lazygit/releases/latest" | grep -Po '"tag_name": "v\K[^"]*')
    curl -Lo lazygit.tar.gz "https://github.com/jesseduffield/lazygit/releases/latest/download/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz"
    tar xf lazygit.tar.gz lazygit
    sudo install lazygit /usr/local/bin
    rm lazygit.tar.gz lazygit
elif [[ "$OS" == "macos" ]]; then
    # Install Homebrew if not installed
    if ! command -v brew &> /dev/null; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install neovim ripgrep lazygit derailed/k9s/k9s bear wget maccy ranger tmux
fi

# Install k9s on Linux
if [[ "$OS" == "linux" ]]; then
    # Using LinuxBrew if available, otherwise try apt
    if command -v brew &> /dev/null; then
        brew install derailed/k9s/k9s
    else
        # Add k9s repo and install via apt
        curl -sS https://webinstall.dev/k9s | bash
    fi
fi

# Install nvm and Node.js
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install 22
node -v
nvm current
npm -v

# Install devcontainers CLI
npm install -g @devcontainers/cli

# Install Miniconda
if [[ "$OS" == "macos" ]]; then
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-arm64.sh"
else
    MINICONDA_URL="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
fi
wget $MINICONDA_URL -O ~/miniconda.sh
bash ~/miniconda.sh -b -p $HOME/miniconda
rm ~/miniconda.sh

# Add conda to path for current session
export PATH="$HOME/miniconda/bin:$PATH"

# Install aider
python -m pip install aider-install
aider-install

# Create config directories
mkdir -p ~/.config

# Create symlinks
ln -sf ~/.dotfiles/nvim ~/.config

# OS-specific symlinks
if [[ "$OS" == "macos" ]]; then
    mkdir -p ~/.config
    ln -sf ~/.dotfiles/ghostty ~/.config
    mkdir -p ~/Library/"Application Support"/"Leader Key"
    ln -sf ~/.dotfiles/leaderkey/config.json ~/Library/"Application Support"/"Leader Key"/config.json
fi

echo "Setup complete for $OS"
