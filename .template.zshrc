# template for .zshrc (extend with your own things)

# additional source required to make conda work in tmux (in addition to the other code mentioned in readme)
source ~/miniconda3/etc/profile.d/conda.sh

# `claude`/`opencode` functions and `claude-setup`/`opencode-setup` commands are
# installed and kept current automatically by ~/.dotfiles/setup.sh -- no need
# to copy them in here.
alias ls="tree -L 1"
