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
    sudo apt-get install -y curl wget git build-essential ripgrep fd-find bear ranger tmux unzip python3-venv

    # fd-find installs its binary as `fdfind` on Debian/Ubuntu; symlink it to
    # the `fd` name everything (Telescope, etc.) actually looks for.
    mkdir -p ~/.local/bin
    if ! command -v fd &> /dev/null && command -v fdfind &> /dev/null; then
        ln -sf "$(command -v fdfind)" ~/.local/bin/fd
    fi

    # Install neovim from its own stable release tarball (skip if already
    # on PATH), not the neovim-ppa/unstable PPA this used to pull from:
    # that's a daily-build channel that intermittently ships a
    # half-published package set ("required packages have not yet been
    # created or been moved out of Incoming"), which fails the whole apt
    # transaction -- including unrelated packages like bear -- and aborts
    # this entire script. Ubuntu's own archived neovim also lags behind
    # what this config needs: vim.lsp.enable() and
    # vim.treesitter.query.set() both require >= 0.11.
    if ! command -v nvim &> /dev/null; then
        case "$(uname -m)" in
            x86_64) NVIM_ARCH="x86_64" ;;
            aarch64) NVIM_ARCH="arm64" ;;
            *) echo "Unsupported architecture for neovim: $(uname -m)" >&2; exit 1 ;;
        esac
        NVIM_TMP="$(mktemp -d)"
        curl -fsSL -o "$NVIM_TMP/nvim.tar.gz" "https://github.com/neovim/neovim/releases/latest/download/nvim-linux-${NVIM_ARCH}.tar.gz"
        sudo mkdir -p /opt/nvim
        sudo tar -xzf "$NVIM_TMP/nvim.tar.gz" -C /opt/nvim --strip-components=1
        sudo ln -sf /opt/nvim/bin/nvim /usr/local/bin/nvim
        rm -rf "$NVIM_TMP"
    fi

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
    brew install neovim ripgrep fd lazygit derailed/k9s/k9s bear wget maccy ranger tmux openjdk openjdk@21
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

# Install omp (Oh My Pi coding agent CLI). The installer drops the binary in
# ~/.local/bin, which isn't necessarily on PATH yet for this already-running
# shell (it wires PATH into ~/.bashrc/~/.zshrc for *future* shells) -- export
# it here so the omp calls a few lines down actually find it.
if ! command -v omp &> /dev/null; then
    curl -fsSL https://omp.sh/install | sh
fi
export PATH="$HOME/.local/bin:$PATH"

# Create config directories
mkdir -p ~/.config

# Create symlinks
ln -sf ~/.dotfiles/config/nvim ~/.config

# omp config: symlink the versioned provider/agent settings and plugin lock
# file into place. omp-plugins.lock.json is safe to symlink (it's the
# declarative "what should be enabled" record and doesn't block a real
# install). marketplaces.json and plugins/installed_plugins.json are
# versioned in config/omp/ for visibility only and deliberately NOT
# symlinked: they're runtime bookkeeping keyed by absolute cache paths, and
# pre-seeding either of them makes omp believe a marketplace/plugin is
# already present without checking whether the actual cache/node_modules
# content exists -- verified empirically: with a stale entry in place but
# its cache deleted, both `omp plugin marketplace add` and
# `omp plugin install` report "already exists"/"already installed" and
# skip re-fetching, leaving a broken reference. The commands below are the
# only safe way to (re)materialize them on any machine.
mkdir -p ~/.omp/agent ~/.omp/plugins
ln -sf ~/.dotfiles/config/omp/config.yml ~/.omp/agent/config.yml
ln -sf ~/.dotfiles/config/omp/plugins/omp-plugins.lock.json ~/.omp/plugins/omp-plugins.lock.json

# Reproduce the configured marketplace and plugin. Non-fatal: a fresh
# marketplace/network hiccup here must not abort the rest of setup.sh.
omp plugin marketplace add anthropics/claude-plugins-official || true
omp plugin install clangd-lsp@claude-plugins-official || true

# OS-specific symlinks
if [[ "$OS" == "macos" ]]; then
    ln -sf ~/.dotfiles/config/ghostty ~/.config
    mkdir -p ~/Library/"Application Support"/"Leader Key"
    ln -sf ~/.dotfiles/config/leaderkey/config.json ~/Library/"Application Support"/"Leader Key"/config.json
fi

# ~/.local/bin entrypoints for the devcontainer setup scripts, so nothing
# outside this repo needs to hardcode a scripts/ path.
mkdir -p ~/.local/bin
ln -sf ~/.dotfiles/scripts/devcontainer/setup-claude-devcontainer.sh ~/.local/bin/claude-setup
ln -sf ~/.dotfiles/scripts/devcontainer/setup-opencode-devcontainer.sh ~/.local/bin/opencode-setup
ln -sf ~/.dotfiles/scripts/projects/new-python-project.sh ~/.local/bin/new-python-project
ln -sf ~/.dotfiles/scripts/projects/new-cpp-project.sh ~/.local/bin/new-cpp-project

# Safely rewrite ~/.zshrc: only if the candidate actually differs from what's
# currently there, only after a zsh syntax check, and only after taking a
# timestamped backup of the current file.
commit_zshrc() {
    local candidate="$1"
    local zshrc="$HOME/.zshrc"

    if cmp -s "$candidate" "$zshrc"; then
        rm -f "$candidate"
        return 0
    fi

    if command -v zsh &> /dev/null && ! zsh -n "$candidate" 2> /dev/null; then
        echo "Warning: generated ~/.zshrc failed a zsh syntax check; leaving your ~/.zshrc untouched." >&2
        rm -f "$candidate"
        return 1
    fi

    cp "$zshrc" "$zshrc.bak.$(date +%Y%m%d%H%M%S)"
    mv "$candidate" "$zshrc"
    echo "Updated $zshrc (previous version backed up alongside it)"
}

# Keep the devcontainer helper functions in ~/.zshrc current, without ever
# touching anything else you keep there.
sync_devcontainer_helpers() {
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
    docker exec -it "$(devcontainer up --config .devcontainer/claude/devcontainer.json --workspace-folder . --remove-existing-container | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)" claude
}

opencode() {
    docker exec -it "$(devcontainer up --config .devcontainer/opencode/devcontainer.json --workspace-folder . --remove-existing-container | grep -o '"containerId":"[^"]*"' | cut -d'"' -f4)" opencode
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

    commit_zshrc "$final" || true
}

# Keep a ranger alias current in ~/.zshrc: ". ranger" (sourcing ranger
# instead of exec'ing it) makes ranger cd the *current* shell into the last
# directory you visited before quitting, instead of leaving you back where
# you started. See https://github.com/ranger/ranger/issues/2679.
sync_ranger_alias() {
    local zshrc="$HOME/.zshrc"
    local begin_marker="# >>> dotfiles ranger alias >>>"
    local end_marker="# <<< dotfiles ranger alias <<<"

    touch "$zshrc"

    local block
    block="$(cat <<'BLOCK'
alias ranger=". ranger"
BLOCK
)"

    local begin_line end_line
    begin_line="$(grep -nF "$begin_marker" "$zshrc" 2>/dev/null | head -1 | cut -d: -f1)" || true
    end_line="$(grep -nF "$end_marker" "$zshrc" 2>/dev/null | head -1 | cut -d: -f1)" || true

    local final
    final="$(mktemp)"
    if [ -n "${begin_line:-}" ] && [ -n "${end_line:-}" ] && [ "$end_line" -gt "$begin_line" ]; then
        # Existing block: replace its contents in place, keep everything else untouched.
        { head -n "$begin_line" "$zshrc"; printf '%s\n' "$block"; tail -n "+$end_line" "$zshrc"; } > "$final"
    else
        # No block yet: append a fresh one at the end.
        { cat "$zshrc"; echo ""; echo "$begin_marker"; printf '%s\n' "$block"; echo "$end_marker"; } > "$final"
    fi

    commit_zshrc "$final" || true
}

# Keep the Homebrew openjdk PATH entries current in ~/.zshrc (macOS only):
# both openjdk formulae are keg-only (Homebrew won't symlink them onto PATH
# itself, since multiple JDKs can coexist), and openjdk@21 is listed last so
# it wins over plain openjdk when both are on PATH.
sync_java_path() {
    local zshrc="$HOME/.zshrc"
    local begin_marker="# >>> dotfiles java path >>>"
    local end_marker="# <<< dotfiles java path <<<"

    touch "$zshrc"

    # Drop the old unmanaged raw exports (from `brew install openjdk`'s own
    # manual-setup suggestion) so they don't sit duplicated next to the
    # managed block below.
    local work
    work="$(mktemp)"
    grep -vF \
        -e 'export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"' \
        -e 'export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"' \
        "$zshrc" > "$work" || true

    local block
    block="$(cat <<'BLOCK'
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
export PATH="/opt/homebrew/opt/openjdk@21/bin:$PATH"
BLOCK
)"

    local begin_line end_line
    begin_line="$(grep -nF "$begin_marker" "$work" 2>/dev/null | head -1 | cut -d: -f1)" || true
    end_line="$(grep -nF "$end_marker" "$work" 2>/dev/null | head -1 | cut -d: -f1)" || true

    local final
    final="$(mktemp)"
    if [ -n "${begin_line:-}" ] && [ -n "${end_line:-}" ] && [ "$end_line" -gt "$begin_line" ]; then
        { head -n "$begin_line" "$work"; printf '%s\n' "$block"; tail -n "+$end_line" "$work"; } > "$final"
    else
        { cat "$work"; echo ""; echo "$begin_marker"; printf '%s\n' "$block"; echo "$end_marker"; } > "$final"
    fi
    rm -f "$work"

    commit_zshrc "$final" || true
}

# Keep conda usable in tmux panes / nvim terminals current in ~/.zshrc: let
# `conda init` manage its own block (safe to re-run), wrap that block in the
# CONDA_SHLVL guard from
# https://nielscautaerts.xyz/make-active-conda-environment-persist-in-neovim-terminal.html
# so an already-active env survives into nested shells, and ensure the
# tmux-specific conda.sh source line is present. Never touches anything else.
sync_conda_tmux_persistence() {
    local zshrc="$HOME/.zshrc"
    touch "$zshrc"

    # Run `conda init` against a scratch $HOME instead of the real file
    # directly: it always rewrites the target rc file (even a no-op-looking
    # one may reformat something), so touching ~/.zshrc with it mid-function
    # would make every run look like a change. Compute the full result in
    # scratch, then do exactly one clean comparison against the real file.
    local workdir
    workdir="$(mktemp -d)"
    local candidate="$workdir/.zshrc"
    cp "$zshrc" "$candidate"

    if command -v conda &> /dev/null; then
        HOME="$workdir" conda init zsh > /dev/null 2>&1 || true
    fi

    local begin_marker="# >>> conda initialize >>>"
    local end_marker="# <<< conda initialize <<<"
    local wrap_begin='if [[ -z "${CONDA_SHLVL}" ]]; then'
    local begin_line end_line
    begin_line="$(grep -nF "$begin_marker" "$candidate" 2>/dev/null | head -1 | cut -d: -f1)" || true
    end_line="$(grep -nF "$end_marker" "$candidate" 2>/dev/null | head -1 | cut -d: -f1)" || true

    if [ -n "${begin_line:-}" ] && [ -n "${end_line:-}" ]; then
        local prev_line=$((begin_line - 1))
        local prev_text=""
        [ "$prev_line" -ge 1 ] && prev_text="$(sed -n "${prev_line}p" "$candidate")"
        local next_line=$((end_line + 1))
        local next_text
        next_text="$(sed -n "${next_line}p" "$candidate")"

        if [ "$prev_text" != "$wrap_begin" ] || [ "$next_text" != "fi" ]; then
            local wrapped="$workdir/wrapped"
            {
                [ "$prev_line" -ge 1 ] && head -n "$prev_line" "$candidate"
                echo "$wrap_begin"
                sed -n "${begin_line},${end_line}p" "$candidate"
                echo "fi"
                tail -n "+$next_line" "$candidate"
            } > "$wrapped"
            mv "$wrapped" "$candidate"
        fi
    fi

    # `conda init` unconditionally comments out any standalone conda.sh
    # source line it finds elsewhere in the file, thinking it's redundant
    # with its own block above. It isn't here -- this one is deliberately
    # unguarded (unlike the block above) so the `conda` shell function,
    # not just inherited env vars, is available in tmux panes / nvim
    # terminals. Strip every trace of this pair (active, disabled by
    # conda, or orphaned by an older buggy pass of this function) and
    # re-add exactly one canonical, active copy.
    local stripped="$workdir/stripped"
    grep -vF \
        -e "# additional source required to make conda work in tmux" \
        -e "source ~/miniconda3/etc/profile.d/conda.sh" \
        "$candidate" > "$stripped" || true
    grep -v 'commented out by conda initialize' "$stripped" > "$candidate" || true

    if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        {
            echo ""
            echo "# additional source required to make conda work in tmux"
            echo "source ~/miniconda3/etc/profile.d/conda.sh"
        } >> "$candidate"
    fi

    local squeezed="$workdir/squeezed"
    cat -s "$candidate" > "$squeezed"
    mv "$squeezed" "$candidate"

    local final
    final="$(mktemp)"
    cp "$candidate" "$final"
    rm -rf "$workdir"

    commit_zshrc "$final" || true
}

sync_devcontainer_helpers || true
sync_ranger_alias || true
if [[ "$OS" == "macos" ]]; then
    sync_java_path || true
fi
sync_conda_tmux_persistence || true

echo "Setup complete for $OS"

if [ ! -f ~/.omp/agent/.env ]; then
    echo ""
    echo "==> One more step: add your OpenRouter key so the omp REPL (<C-a> in nvim) can reach a model:"
    echo "      echo 'OPENROUTER_API_KEY=sk-...' > ~/.omp/agent/.env"
fi
