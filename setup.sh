#!/bin/bash


# exit if not macOS, because dependencies below only work for mac
if [[ "$(uname)" != "Darwin" ]]; then
  echo "This script is intended for macOS only."
  exit 1
fi


echo "installing dependencies ..."

# nodejs, per the website
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
\. "$HOME/.nvm/nvm.sh"
nvm install 22
node -v
nvm current
npm -v

# brew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# other dependencies
brew install neovim ripgrep lazygit

# conda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh -O ~/miniconda.sh
bash ~/miniconda.sh -b -p $HOME/miniconda

# aider 
python -m pip install aider-install
aider-install

# TODO: extend .zshrc, but do not version the entire thing or symlink it

# create symlinks
ln -s ~/.dotfiles/ghostty ~/.config/ghostty
ln -s ~/.dotfiles/nvim ~/.config/nvim

echo "setup complete."
