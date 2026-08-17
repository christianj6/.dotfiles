# .dotfiles

Miscellaneous configuration files for a reproducible workspace.

## Set Up macOS

1. Install core apps
    - Sunsama
    - 1Password
    - Arc Browser
        - 1Password Extension
        - Vimium Extension
    - Ghostty
    - Leader Key
2. [Set Up Terminal Workspace](#set-up-terminal-workspace)
3. Optional apps
    - ChatGPT
    - Rancher Desktop

## Set Up Terminal Workspace

```bash
git clone ...
cd .dotfiles/
bash ./setup.sh
nvim
```

`setup.sh` installs and configures Homebrew and conda automatically. You'll probably still want to configure a Nerd Font by hand, and it's a good idea to put some aliases etc. in your `.zshrc` (see `.template.zshrc` for a starting point) — the above gets you about 95% of the way there.

## `setup.sh` — the one-stop workspace configuration tool

Anything this repo needs on a machine belongs in `setup.sh`, not in a manual step written here in the README. It's an idempotent *apply* script, not a one-shot installer: pull this repo onto any machine (or one you've already set up) and run `bash ./setup.sh` — it converges the workspace to the state this repo describes (installed tools, symlinked configs, `~/.local/bin` entrypoints, a couple of small managed blocks in your `~/.zshrc`) without redoing finished work or touching anything you've added yourself. Re-run it any time, as often as you want.

How it stays safe to re-run:
- Every install step checks first (`command -v`, a directory/file test, an existing-install check) and skips whatever's already done.
- Anything it writes into `~/.zshrc` lives inside clearly marked blocks (`# >>> ... >>>` / `# <<< ... <<<` — the same convention `conda init` and Rancher Desktop already use in that file) or is an exact, known-string match (e.g. retiring an old alias). It never touches anything else in your `~/.zshrc`.
- Before writing, it diffs the candidate against the file's pre-change state and skips the write if nothing changed, syntax-checks the result with `zsh -n`, and takes a timestamped backup (`~/.zshrc.bak.<timestamp>`) right before overwriting anything.

If you find yourself writing "now go manually do X" in this README, that's usually a sign `setup.sh` should be doing X instead.

## Utility Scripts

The `/scripts` directory:

- **`new-python-project.sh`** — scaffolds a new Python project: conda env, pre-commit, git init.

- **`devcontainers/`** — `setup-claude-devcontainer.sh` / `setup-opencode-devcontainer.sh` copy a devcontainer config into any project and start it.
    - `setup.sh` symlinks both into `~/.local/bin` as `claude-setup` / `opencode-setup`.
    - `setup.sh` also keeps the matching `claude` / `opencode` shell functions current inside a marked `~/.zshrc` block (`# >>> dotfiles devcontainer helpers >>>` ... `<<<`), never touching anything else in that file.
    - `scripts/setup-claude-devcontainer.sh` / `setup-opencode-devcontainer.sh` still exist too, as symlinks into `devcontainers/`, for any already-deployed `.zshrc` referencing the pre-reorg path.

- **`trello-notes/`** — Trello + LLM note-sorting automation: `merge_trello_cards.py`, `sort_trello_inbox.py`, `create_project_plan.py`, `llm_note_sorter.py`, the `trello` API client package, and a `prompts/` folder with the LLM prompt and PDF-parsing instructions.
    - Setup: `pip install -r scripts/trello-notes/requirements.txt`
    - Run from that directory (`cd scripts/trello-notes`) — some scripts read files like `prompt.txt` / `priorities.json` relative to the current directory.

## Additional Resources

- **Conda persisting into nvim/tmux child shells** — `setup.sh` automatically applies [this trick](https://nielscautaerts.xyz/make-active-conda-environment-persist-in-neovim-terminal.html): it runs `conda init zsh`, wraps the result in `if [[ -z "${CONDA_SHLVL}" ]]; then ... fi`, and adds the tmux-specific `source ~/miniconda3/etc/profile.d/conda.sh` line, so an already-activated conda env survives into nested shells instead of resetting. Nothing to do by hand. (I typically pair this with project-specific `.zshrc` aliases that activate a conda env before starting nvim in a project directory.)

- **`ranger` quit-and-cd** — see [this issue](https://github.com/ranger/ranger/issues/2679) for making `ranger` quit into whatever directory you navigated to, instead of back to where you started.
