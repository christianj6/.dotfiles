# .dotfiles

Miscellaneous configuration files for a reproducible workspace.

## How to use

```bash
git clone ...
cd .dotfiles/
bash ./setup.sh
nvim
```

`setup.sh` is idempotent — safe to re-run any time, on any machine, to pick up changes.

Linux support assumes Ubuntu/Debian (`apt-get`-based); other distros aren't supported. On EC2 (or similarly small cloud instances), use at least 8GB RAM — `omp` is a self-contained bun/V8 binary that gets silently OOM-killed (a bare `Killed`, no other output) on the 1GB `t2/t3.micro` free-tier default. `setup.sh` adds a swapfile as a safety net below 2GB RAM, but a properly-sized instance is what's actually confirmed to just work.

## Additional steps

- Install manually: Sunsama, 1Password, Arc Browser (+ 1Password and Vimium extensions), Ghostty, Leader Key, Wireshark. Optional: ChatGPT, Rancher Desktop, Antigravity.
- Configure a Nerd Font.
- `templates/` holds copy-paste starting points, never read automatically: `zshrc.example` for your own `~/.zshrc` aliases, `env.example` for `.env` at the repo root (aider preferences + `scripts/trello` secrets), `omp.env.example` for `~/.omp/agent/.env` (OpenRouter key for the omp nvim REPL).
- `claude-setup [dir]` / `opencode-setup [dir]` copy the `.devcontainer/claude/` or `.devcontainer/opencode/` sandboxed-devcontainer template (network allowlist, CLI preinstalled) into another project and start it. `scripts/projects/` has project scaffolders; `scripts/trello/` has Trello/note-sorting automation.
- `config/omp/` versions the omp CLI's config: `config.yml`, `models.yml` and `plugins/omp-plugins.lock.json` are symlinked into place by `setup.sh` (which also installs the `omp` CLI itself and the `clangd-lsp` plugin); `marketplaces.json` and `plugins/installed_plugins.json` are committed for visibility only — they're absolute-path runtime bookkeeping that `setup.sh` regenerates via `omp plugin marketplace add`/`omp plugin install` rather than copying into place. The default model routes through OpenRouter (`openrouter/anthropic/claude-opus-5:xhigh`) so a fresh machine only needs one API key — see `templates/omp.env.example`. `models.yml` carries provider overrides: currently the `opencode-go` compat knob that sends a stable per-session id in `x-opencode-session` (the Console Go gateway 400s without it; newer omp bundles do this natively, the override is harmless there).
- `setup.sh` installs the herdr terminal workspace manager (https://herdr.dev, AI-agent pane multiplexer) alongside omp: `config/herdr/plugins/omp-watch/` is a versioned herdr plugin that reports omp's real lifecycle state to the sidebar by tailing its own session transcript (herdr's native omp integration is intentionally *not* installed — omp v17.3.4's extension API never delivers a lifecycle event, and a second installed-but-silent integration would only compete with this plugin for status authority; see `TODO.md` history if it resurfaces); claude's integration reports session identity for restore only. `config/herdr/config.toml` is symlinked into `~/.config/herdr/` (onboarding skipped, login-shell panes on macOS), the herdr agent skill lands in the omp/claude skill dirs alongside a versioned companion skill (`config/herdr/skills/herdr-workstreams/`) that teaches agents to start workstreams — workspaces, panes, git worktrees — and to message each other (transcript-confirmed agent-to-agent comms via the `omp-peer` helper installed on PATH) through the herdr CLI, and zsh completions are sourced straight from the binary. The binary self-updates via `herdr update`.


## References

- [Persisting an active conda env into nvim/tmux child shells](https://nielscautaerts.xyz/make-active-conda-environment-persist-in-neovim-terminal.html) — handled automatically by `setup.sh`.
- [Making `ranger` quit into the directory you navigated to](https://github.com/ranger/ranger/issues/2679)
