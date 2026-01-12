# template for .zshrc (extend with your own things)

# additional source required to make conda work in tmux (in addition to the other code mentioned in readme)
source ~/miniconda3/etc/profile.d/conda.sh

claude() {
    docker exec -it "$(devcontainer up --workspace-folder . | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)" claude
}

alias claude-setup="~/.dotfiles/scripts/setup-claude-devcontainer.sh"
alias ls="tree -L 1"
