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

# Shared retry policy for one-shot installer downloads: cloud/CI networks
# occasionally return a transient 5xx (e.g. the 502 from omp.sh's install
# endpoint that once took this whole script down) or refuse a connection
# while still settling right after boot, and with `set -e` that would
# otherwise abort this entire script over one bad request.
CURL_RETRY=(--retry 3 --retry-delay 2 --retry-connrefused)

echo "Installing dependencies for $OS..."

# Small cloud instances (e.g. EC2 t2/t3.micro's 1GB RAM) don't leave enough
# headroom for a bun-based binary like omp to even start, let alone run
# node/npm installs alongside it -- both silently die with a bare "Killed"
# (the kernel's OOM killer, not an omp or setup.sh bug). Add swap once, if
# there's noticeably less than 2GB of RAM and none is already configured.
# Non-fatal: a failure here (e.g. a filesystem that rejects swapfiles) must
# not abort the rest of setup.sh.
ensure_swap() {
    [ -f /swapfile ] && return 0
    [ "$(swapon --show | wc -l)" -gt 0 ] && return 0

    local mem_kb
    mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
    [ "$mem_kb" -ge 2097152 ] && return 0

    echo "Low memory detected ($((mem_kb / 1024))MB RAM) -- adding a 2GB swapfile so later installs (npm, omp) don't get OOM-killed"
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab > /dev/null
}

# Install system packages
if [[ "$OS" == "linux" ]]; then
    ensure_swap || true

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
        curl -fsSL "${CURL_RETRY[@]}" -o "$NVIM_TMP/nvim.tar.gz" "https://github.com/neovim/neovim/releases/latest/download/nvim-linux-${NVIM_ARCH}.tar.gz"
        sudo mkdir -p /opt/nvim
        sudo tar -xzf "$NVIM_TMP/nvim.tar.gz" -C /opt/nvim --strip-components=1
        sudo ln -sf /opt/nvim/bin/nvim /usr/local/bin/nvim
        rm -rf "$NVIM_TMP"
    fi

    # Install lazygit (skip if already on PATH)
    if ! command -v lazygit &> /dev/null; then
        LAZYGIT_TMP="$(mktemp -d)"
        LAZYGIT_VERSION=$(curl -fsS "${CURL_RETRY[@]}" "https://api.github.com/repos/jesseduffield/lazygit/releases/latest" | grep -Po '"tag_name": "v\K[^"]*')
        curl -fLo "$LAZYGIT_TMP/lazygit.tar.gz" "${CURL_RETRY[@]}" "https://github.com/jesseduffield/lazygit/releases/latest/download/lazygit_${LAZYGIT_VERSION}_Linux_x86_64.tar.gz"
        tar xf "$LAZYGIT_TMP/lazygit.tar.gz" -C "$LAZYGIT_TMP" lazygit
        sudo install "$LAZYGIT_TMP/lazygit" /usr/local/bin
        rm -rf "$LAZYGIT_TMP"
    fi

    # Install k9s (skip if already on PATH)
    if ! command -v k9s &> /dev/null; then
        if command -v brew &> /dev/null; then
            brew install derailed/k9s/k9s
        else
            curl -fsS "${CURL_RETRY[@]}" https://webinstall.dev/k9s | bash
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
    curl -fsSL "${CURL_RETRY[@]}" https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
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
    wget --tries=3 --waitretry=2 "$MINICONDA_URL" -O ~/miniconda.sh
    bash ~/miniconda.sh -b -p "$HOME/miniconda3"
    rm ~/miniconda.sh
fi

# Add conda to path for current session
export PATH="$HOME/miniconda3/bin:$PATH"

# Install aider. Non-fatal: aider-install's own `uv tool update-shell` step
# can exit non-zero when it finds ~/.local/bin already referenced in
# .bashrc/.profile (e.g. Ubuntu's stock /etc/skel/.profile snippet) while
# this non-interactive script's own shell doesn't have it live yet -- uv
# treats that as an error ("Bash configuration files are already
# up-to-date") even though the actual aider binary already installed fine
# by that point. Must not abort the rest of setup.sh over it.
python -m pip install aider-install
aider-install || true

# Install omp (Oh My Pi coding agent CLI). The installer drops the binary in
# ~/.local/bin. Export it here so the omp calls a few lines down find it in
# this already-running shell, and persist it in ~/.bashrc/~/.profile so NEW
# shells (like the prompt after setup.sh finishes) also find it -- without
# that, `omp` fails with "command not found" in the very next shell even
# though the binary is installed.
if ! command -v omp &> /dev/null; then
    curl -fsSL "${CURL_RETRY[@]}" https://omp.sh/install | sh
fi
export PATH="$HOME/.local/bin:$PATH"

if ! grep -qF 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
fi
if ! grep -qF 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.profile" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.profile"
fi

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
ln -sf ~/.dotfiles/config/omp/models.yml ~/.omp/agent/models.yml
ln -sf ~/.dotfiles/config/omp/plugins/omp-plugins.lock.json ~/.omp/plugins/omp-plugins.lock.json

# Reproduce the configured marketplace and plugin. Non-fatal: a fresh
# marketplace/network hiccup here must not abort the rest of setup.sh.
omp plugin marketplace add anthropics/claude-plugins-official || true
omp plugin install clangd-lsp@claude-plugins-official || true

# Install herdr (https://herdr.dev) terminal workspace manager. Same pattern
# as omp above: the curl installer is identical on macOS and Linux, drops the
# binary in ~/.local/bin (already exported and persisted above), and any
# pre-existing install -- e.g. via Homebrew -- is left alone. Required, not
# `|| true`: herdr is a key component, same bar as the omp install itself.
if ! command -v herdr &> /dev/null; then
    curl -fsSL "${CURL_RETRY[@]}" https://herdr.dev/install.sh | sh
fi

# Install the agent integrations for the agents this workspace actually runs.
# claude reports session identity for restore while its state stays on screen
# detection (no lifecycle authority conflict -- see agents doc). Re-running is
# also the update path -- a stale integration shows "outdated" in
# `herdr integration status` and install rewrites it -- so this is
# deliberately NOT gated on presence. Non-fatal: an install needs the agent's
# config dir to exist (e.g. no ~/.claude on a machine that never ran claude),
# and that must not abort setup.sh.
#
# omp is deliberately NOT installed here (and was uninstalled 2026-09-04 after
# being installed by an earlier pass of this script). herdr lists omp as a
# "lifecycle authority" agent, but omp v17.3.4's extension API never delivers
# a single lifecycle event through a live agent turn -- verified exhaustively,
# including a minimal bare-bones test extension -- so the integration sits
# installed-but-silent. herdr's own docs warn against a second report-agent
# source running "next to a Herdr-managed integration" (it competes for
# authority instead of being additive), which is exactly what was happening:
# the dead native integration and config/herdr/plugins/omp-watch/ (this
# repo's session-transcript watcher, the one mechanism that actually works)
# were both claiming the same `--agent omp` on the same pane. Installing the
# native integration here would silently reintroduce that conflict on every
# fresh machine. If a future omp release fixes the extension API, revisit.
herdr integration install claude || true

# herdr config: symlink the versioned settings into ~/.config/herdr. The
# versioned file carries onboarding=false and macOS login-shell panes; the
# file the app writes on first run ("onboarding = false") is a strict subset,
# so the symlink never clobbers a real setting.
mkdir -p ~/.config/herdr
ln -sf ~/.dotfiles/config/herdr/config.toml ~/.config/herdr/config.toml

# Install the herdr skill into the agent skill dirs: teaches agents running
# inside a herdr pane (HERDR_ENV=1) to drive herdr -- split panes, read
# sibling output, wait on other agents. omp follows the pi agent layout
# (~/.omp/agent/skills/); claude uses ~/.claude/skills/. Non-fatal: a failed
# fetch must not abort setup.sh.
mkdir -p ~/.omp/agent/skills/herdr ~/.claude/skills/herdr
curl -fsSL "${CURL_RETRY[@]}" https://raw.githubusercontent.com/herdrdev/herdr/master/skills/herdr/SKILL.md -o ~/.omp/agent/skills/herdr/SKILL.md || true
curl -fsSL "${CURL_RETRY[@]}" https://raw.githubusercontent.com/herdrdev/herdr/master/skills/herdr/SKILL.md -o ~/.claude/skills/herdr/SKILL.md || true

# Companion skill: workstream + peer-comms recipes -- create/list/clean up
# workspaces ("spaces"), panes, and git worktrees. Unlike the upstream fetch
# above (re-fetched from GitHub on every run), this one is versioned in the
# repo and copied, so local edits survive and offline runs still get it.
# Non-fatal: a missing repo file must not abort setup.sh.
mkdir -p ~/.omp/agent/skills/herdr-workstreams ~/.claude/skills/herdr-workstreams
cp ~/.dotfiles/config/herdr/skills/herdr-workstreams/SKILL.md ~/.omp/agent/skills/herdr-workstreams/SKILL.md || true
cp ~/.dotfiles/config/herdr/skills/herdr-workstreams/SKILL.md ~/.claude/skills/herdr-workstreams/SKILL.md || true

# The peer-comms helper goes on PATH (not in the skill dirs) so every agent
# can call it regardless of which agent's skill dir it was taught from.
mkdir -p ~/.local/bin
cp ~/.dotfiles/config/herdr/skills/herdr-workstreams/peer.py ~/.local/bin/omp-peer || true
chmod +x ~/.local/bin/omp-peer 2>/dev/null || true

# terminal-browser (https://terminal-browser.com): a real browser that
# renders inside the terminal via kitty graphics (ghostty/herdr already
# carry it; `terminal-browser setup` only touches VS Code-family editors).
# Install is required (same bar as herdr); `setup` is non-fatal.
if ! command -v terminal-browser &> /dev/null; then
    curl -fsSL "${CURL_RETRY[@]}" https://terminal-browser.sh/install | bash
fi
terminal-browser setup || true

# Agent skill copies + machine banner. The tool's own skill manifest lists
# only claude/codex/cursor/gemini -- omp is absent -- so both agents get
# the skill from here. Per agent dir, two files:
# (1) terminal-browser/SKILL.md = canonical command reference + banner.
#     Rebuilt on every run as canonical + banner.md, so upgrades refresh
#     the reference and the banner always rides along. A COPY, not the
#     symlink the tool would place itself: the banner must survive
#     `terminal-browser setup`/upgrade, and its linkSkills() deliberately
#     leaves non-symlink copies alone (verified in its source).
# (2) terminal-browser-quirks/ = versioned companion skill: standard usage
#     flow + the working CDP path (the v0.8.0 wrapper's
#     `terminal-browser action --` cannot reach the CDP port on this
#     machine -- IPv6/localhost resolution vs IPv4-only listener; agents
#     drive via the bundled agent-browser CLI over http://127.0.0.1:<port>).
#     Retire it when an upgrade fixes the wrapper.
_TB_CANONICAL=~/.local/share/terminal-browser/app/skills/default/terminal-browser/SKILL.md
for d in ~/.omp/agent/skills ~/.claude/skills; do
    # Replace any pre-existing symlink entry (e.g. one the tool itself
    # placed) with a real dir BEFORE writing: cat-ing through a symlink
    # to the canonical dir would clobber the upstream file (observed
    # 2026-09-07; recovered from the release tarball -- see the block
    # comment). `rm -f` on the link, THEN mkdir (the mkdir must come
    # after removal, or the removed link leaves no parent dir behind).
    [ -L "$d/terminal-browser" ] && rm -f "$d/terminal-browser"
    [ -L "$d/terminal-browser/SKILL.md" ] && rm -f "$d/terminal-browser/SKILL.md"
    mkdir -p "$d/terminal-browser" "$d/terminal-browser-quirks"
    cat "$_TB_CANONICAL" ~/.dotfiles/config/herdr/skills/terminal-browser/banner.md \
        > "$d/terminal-browser/SKILL.md" 2>/dev/null \
        || echo "warning: terminal-browser canonical skill not found at $_TB_CANONICAL" >&2
    cp ~/.dotfiles/config/herdr/skills/terminal-browser-quirks/SKILL.md \
        "$d/terminal-browser-quirks/SKILL.md" || true
done

# Link the omp session watcher plugin: reports omp agent state to herdr by
# tailing omp's own session transcript, since omp's extension/hook API does
# not deliver lifecycle events to file-discovered extensions (verified
# empirically -- neither herdr's own omp integration nor a minimal test
# extension ever received a single event through a live agent turn) and
# herdr ships no screen-manifest fallback for omp either. Idempotent and
# non-fatal: needs a running herdr server, so on a fresh machine this is a
# harmless no-op until the next setup.sh re-run after the first `herdr`
# launch -- same shape as the omp plugin marketplace calls above.
herdr plugin link ~/.dotfiles/config/herdr/plugins/omp-watch || true

# Discord bridge plugin (config/herdr/plugins/agent-discord/): provisions
# the venv for the persistent bot (discord.py is the plugin's one
# non-stdlib dependency -- the notify hook itself is stdlib-only), links
# the plugin, and seeds the config-dir .env from the template WITHOUT ever
# overwriting an existing one (the user's bot token lives only there).
# All non-fatal: a venv/pip failure must not abort setup.sh; run-bot.sh
# prints a clear error into the plugin log if the venv is missing.
if [ ! -x "$HOME/.herdr-discord-venv/bin/python" ]; then
    python3 -m venv "$HOME/.herdr-discord-venv" || true
fi
"$HOME/.herdr-discord-venv/bin/pip" install --quiet --upgrade discord.py || true
herdr plugin link ~/.dotfiles/config/herdr/plugins/agent-discord || true
DISCORD_CFG_DIR="$HOME/.config/herdr/plugins/config/dotfiles.agent-discord"
mkdir -p "$DISCORD_CFG_DIR"
if [ ! -f "$DISCORD_CFG_DIR/.env" ]; then
    cp ~/.dotfiles/config/herdr/plugins/agent-discord/.env.example "$DISCORD_CFG_DIR/.env"
    chmod 600 "$DISCORD_CFG_DIR/.env"
fi

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
ln -sf ~/.dotfiles/scripts/projects/omp-last ~/.local/bin/omp-last

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
    # Only the opencode wrapper remains managed here; the claude() wrapper
    # was removed 2026-09-07 so `claude` in a fresh shell resolves to the
    # native binary (~/.local/bin/claude) -- the wrapper depended on the
    # `devcontainer` CLI, which is not installed, so it made `claude`
    # fail outright. Container claude remains opt-in via `claude-setup`
    # (scripts/devcontainer/) and the .devcontainer/claude/ template.
    # Belt-and-braces drop list: strips the old claude() lines from any
    # zshrc written before this change.
    local zshrc="$HOME/.zshrc"
    local begin_marker="# >>> dotfiles devcontainer helpers >>>"
    local end_marker="# <<< dotfiles devcontainer helpers <<<"

    touch "$zshrc"

    # Drop legacy single-line aliases AND the removed claude() wrapper
    # lines from zshrcs written before 2026-09-07; the managed block below
    # and the ~/.local/bin symlinks above replace them.
    local work
    work="$(mktemp)"
    grep -vF \
        -e "alias claude-setup=\"~/.dotfiles/scripts/setup-claude-devcontainer.sh\"" \
        -e "alias opencode-setup=\"~/.dotfiles/scripts/setup-opencode-devcontainer.sh\"" \
        -e "docker exec -it \"\$(devcontainer up --config .devcontainer/claude/devcontainer.json" \
        "$zshrc" > "$work" || true
    local block
    block="$(cat <<'BLOCK'
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

# Keep herdr shell completions current in ~/.zshrc: source the completion
# script straight from the installed binary on every interactive shell start,
# so completions always match the binary (including after `herdr update`)
# with no cache file to regenerate. compinit is only initialized here when
# nothing earlier in ~/.zshrc has done it already.
sync_herdr_completions() {
    local zshrc="$HOME/.zshrc"
    local begin_marker="# >>> dotfiles herdr completions >>>"
    local end_marker="# <<< dotfiles herdr completions <<<"

    touch "$zshrc"

    local block
    block="$(cat <<'BLOCK'
# herdr completions: generated straight from the installed binary.
if command -v herdr &>/dev/null && [[ -o interactive ]]; then
    if ! (( $+functions[compdef] )); then
        autoload -Uz compinit
        compinit
    fi
    source <(herdr completion zsh)
fi
BLOCK
)"

    local begin_line end_line
    begin_line="$(grep -nF "$begin_marker" "$zshrc" 2>/dev/null | head -1 | cut -d: -f1)" || true
    end_line="$(grep -nF "$end_marker" "$zshrc" 2>/dev/null | head -1 | cut -d: -f1)" || true

    local final
    final="$(mktemp)"
    if [ -n "${begin_line:-}" ] && [ -n "${end_line:-}" ] && [ "$end_line" -gt "$begin_line" ]; then
        { head -n "$begin_line" "$zshrc"; printf '%s\n' "$block"; tail -n "+$end_line" "$zshrc"; } > "$final"
    else
        { cat "$zshrc"; echo ""; echo "$begin_marker"; printf '%s\n' "$block"; echo "$end_marker"; } > "$final"
    fi

    commit_zshrc "$final" || true
}

# Keep the project conda env seam current in ~/.zshrc: a project stamps its
# env name into a .conda-env marker file (new-python-project.sh writes one),
# and every shell activates that env on cd -- replacing the per-project
# "cd && conda activate && nvim" aliases. The future herdr restore guard
# reuses activate_env_for_dir instead of duplicating it (see TODO.md).
sync_env_seam() {
    local zshrc="$HOME/.zshrc"
    local begin_marker="# >>> dotfiles project conda env seam >>>"
    local end_marker="# <<< dotfiles project conda env seam <<<"

    touch "$zshrc"

    local block
    block="$(cat <<'BLOCK'
activate_env_for_dir() {
    local marker="$PWD/.conda-env"
    [[ -f "$marker" ]] || return 0
    local want
    want="$(<"$marker")"
    # The conda shell FUNCTION may not exist yet depending on block order in
    # ~/.zshrc (conda.sh gets sourced at the very end for tmux panes); before
    # that, `conda` resolves to the condabin script, which only PRINTS the
    # activation code instead of modifying this shell. Sourcing the hook
    # script is idempotent and env-neutral.
    [[ "$(whence -w conda 2>/dev/null)" == *function* ]] || \
        { [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]] && source "$HOME/miniconda3/etc/profile.d/conda.sh"; }
    [[ -n "$want" ]] || return 0
    command -v conda &>/dev/null || return 0
    [[ "$CONDA_DEFAULT_ENV" == "$want" ]] && return 0
    conda activate "$want" 2>/dev/null
}
autoload -Uz add-zsh-hook
_env_seam_chpwd() { activate_env_for_dir "$@"; }
add-zsh-hook chpwd _env_seam_chpwd
# Fire once so a shell starting inside a project (e.g. a restored herdr pane)
# gets its env immediately.
activate_env_for_dir
# herdr re-entry: a restored herdr pane comes back as a plain shell in its
# saved project dir; marked projects become nvim right away so the pane is
# editor-first again (omp re-attaches via ctrl-a / omp-last). Skipped inside
# nvim terminals ($NVIM set) and when HERDR_NO_NVIM=1; a deliberate nested
# shell in a project pane is `HERDR_NO_NVIM=1 zsh`.
if [[ -n "${HERDR_ENV:-}" && -z "${NVIM:-}" && -z "${HERDR_NO_NVIM:-}" && -f "$PWD/.conda-env" ]]; then
    exec nvim
fi
BLOCK
)"

    local begin_line end_line
    begin_line="$(grep -nF "$begin_marker" "$zshrc" 2>/dev/null | head -1 | cut -d: -f1)" || true
    end_line="$(grep -nF "$end_marker" "$zshrc" 2>/dev/null | head -1 | cut -d: -f1)" || true

    local final
    final="$(mktemp)"
    if [ -n "${begin_line:-}" ] && [ -n "${end_line:-}" ] && [ "$end_line" -gt "$begin_line" ]; then
        { head -n "$begin_line" "$zshrc"; printf '%s\n' "$block"; tail -n "+$end_line" "$zshrc"; } > "$final"
    else
        { cat "$zshrc"; echo ""; echo "$begin_marker"; printf '%s\n' "$block"; echo "$end_marker"; } > "$final"
    fi

    commit_zshrc "$final" || true
}

sync_devcontainer_helpers || true
sync_ranger_alias || true
sync_herdr_completions || true
sync_env_seam || true
if [[ "$OS" == "macos" ]]; then
    sync_java_path || true
fi
sync_conda_tmux_persistence || true

# Apply the possibly-updated herdr config to a running server so re-runs take
# effect live; a stopped server (or a client/server version skew) just picks
# it up on its next start. Non-fatal either way.
herdr server reload-config || true

echo "Setup complete for $OS"

if [ ! -f ~/.omp/agent/.env ]; then
    echo ""
    echo "==> One more step: add your OpenRouter key so the omp REPL (<C-a> in nvim) can reach a model:"
    echo "      echo 'OPENROUTER_API_KEY=sk-...' > ~/.omp/agent/.env"
fi

# omp, aider, and other tools just went onto PATH via ~/.zshrc / ~/.bashrc /
# ~/.profile, but as a child process this script can't push that into the
# shell that invoked it. Replace this process with a fresh login shell so
# PATH is already correct the moment control returns to the terminal --
# but only when there's an actual terminal to hand back to; a
# non-interactive invocation (CI, a piped script) has no one to type into a
# spawned shell, so fall back to telling the caller instead.
if [ -t 0 ] && [ -t 1 ]; then
    echo ""
    echo "==> Starting a fresh shell so omp/aider are on PATH (exit it to return here)..."
    exec "$SHELL" -l
else
    echo ""
    echo "==> omp, aider, and other tools just went onto PATH -- open a new shell (or run 'exec \$SHELL -l') to use them."
fi
