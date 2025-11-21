# template for .zshrc (extend with your own things)

claude() {
    docker exec -it "$(devcontainer up --workspace-folder . | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)" claude
}

alias ls="tree -L 1"
