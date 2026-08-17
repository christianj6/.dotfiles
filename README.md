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

- Install manually: Sunsama, 1Password, Arc Browser (+ 1Password and Vimium extensions), Ghostty, Leader Key. Optional: ChatGPT, Rancher Desktop.
- Configure a Nerd Font.
- Add your own aliases to `~/.zshrc` — see `.template.zshrc` for a starting point.
- See `scripts/` for devcontainer setup (`claude-setup` / `opencode-setup`), a Python project scaffolder, and Trello/note-sorting automation.

## References

- [Persisting an active conda env into nvim/tmux child shells](https://nielscautaerts.xyz/make-active-conda-environment-persist-in-neovim-terminal.html) — handled automatically by `setup.sh`.
- [Making `ranger` quit into the directory you navigated to](https://github.com/ranger/ranger/issues/2679)
