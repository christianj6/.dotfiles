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

# todo: aider


# create symlinks
ln -s ~/.dotfiles/ghostty ~/.config/ghostty
ln -s ~/.dotfiles/nvim ~/.config/nvim

echo "setup complete."
