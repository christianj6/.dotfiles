#!/bin/bash

# todo: install packages

# Clone the dotfiles repo
git clone --bare https://github.com/christianj6/.dotfiles.git $HOME/.dotfiles

# Create symlinks
ln -s ~/.dotfiles/ghostty ~/.config/ghostty
ln -s ~/.dotfiles/nvim ~/.config/nvim

echo "Dotfiles setup complete!"
