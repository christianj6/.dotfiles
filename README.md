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

## Additional steps

- Install manually: Sunsama, 1Password, Arc Browser (+ 1Password and Vimium extensions), Ghostty, Leader Key, Wireshark. Optional: ChatGPT, Rancher Desktop, Antigravity.
- Configure a Nerd Font.
- `templates/` holds copy-paste starting points, never read automatically: `zshrc.example` for your own `~/.zshrc` aliases, `env.example` for `.env` at the repo root (aider preferences + `scripts/trello` secrets), `omp.env.example` for `~/.omp/agent/.env` (OpenRouter key for the omp nvim REPL).
- `claude-setup [dir]` / `opencode-setup [dir]` copy the `.devcontainer/claude/` or `.devcontainer/opencode/` sandboxed-devcontainer template (network allowlist, CLI preinstalled) into another project and start it. `scripts/projects/` has project scaffolders; `scripts/trello/` has Trello/note-sorting automation.
- `config/omp/config.yml` is symlinked to `~/.omp/agent/config.yml` by `setup.sh`, which also installs the `omp` CLI and its `clangd-lsp` plugin. The default model routes through OpenRouter (`openrouter/anthropic/claude-sonnet-5`) so a fresh machine only needs one API key — see `templates/omp.env.example`.

## References

- [Persisting an active conda env into nvim/tmux child shells](https://nielscautaerts.xyz/make-active-conda-environment-persist-in-neovim-terminal.html) — handled automatically by `setup.sh`.
- [Making `ranger` quit into the directory you navigated to](https://github.com/ranger/ranger/issues/2679)
