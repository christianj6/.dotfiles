# .dotfiles
Miscellaneous configuration files for a reproducible workspace.

***

### Instructions for Setting Up Mac 

1. Install Core Programs
    - Sunsama
    - 1Password 
    - Arc Browser 
        - 1Password Extension
        - Vimium Extension 
    - Ghostty
    - Leader Key
2. Set Up Terminal Workspace (see instructions below)
3. Optional Programs 
    - ChatGPT 
    - Rancher Desktop

You probably need to run some extra commands for brew, conda to work properly.

***

### Set Up Terminal Workspace

```
git clone ...
cd .dotfiles/
bash ./setup.sh
nvim
```
You will probably also need to install various packages and/or configure a Nerd Font, but the above will get you 95%. After this setup, it is a good idea to put some aliases etc. in the .zshrc.

### `setup.sh` — the one-stop workspace configuration tool

Anything this repo needs on a machine belongs in `setup.sh`, not in a manual step written here in the README. It's an idempotent *apply* script, not a one-shot installer: pull this repo onto any machine (or one you've already set up) and run `bash ./setup.sh` — it converges the workspace to the state this repo describes (installed tools, symlinked configs, `~/.local/bin` entrypoints, a couple of small managed blocks in your `~/.zshrc`) without redoing finished work or touching anything you've added yourself. Re-run it any time, as often as you want.

How it stays safe to re-run:
- Every install step checks first (`command -v`, a directory/file test, an existing-install check) and skips whatever's already done.
- Anything it writes into `~/.zshrc` lives inside clearly marked blocks (`# >>> ... >>>` / `# <<< ... <<<` — the same convention `conda init` and Rancher Desktop already use in that file) or is an exact, known-string match (e.g. retiring an old alias). It never touches anything else in your `~/.zshrc`.
- Before writing, it diffs the candidate against the file's pre-change state and skips the write if nothing changed, syntax-checks the result with `zsh -n`, and takes a timestamped backup (`~/.zshrc.bak.<timestamp>`) right before overwriting anything.

If you find yourself writing "now go manually do X" in this README, that's usually a sign `setup.sh` should be doing X instead.

***

### Utility Scripts

The /scripts directory:
- `new-python-project.sh` — scaffold a new Python project (conda env, pre-commit, git init).
- `devcontainers/` — `setup-claude-devcontainer.sh` / `setup-opencode-devcontainer.sh` copy a devcontainer config into any project and start it. `setup.sh` symlinks these into `~/.local/bin` as `claude-setup` / `opencode-setup`, and keeps the matching `claude` / `opencode` shell functions in your `~/.zshrc` current inside a marked block (`# >>> dotfiles devcontainer helpers >>>` / `<<<`) — it never touches anything else in that file, and backs it up (`~/.zshrc.bak.<timestamp>`) before any change. (`scripts/setup-claude-devcontainer.sh` / `setup-opencode-devcontainer.sh` also still exist as symlinks into `devcontainers/`, for any already-deployed `.zshrc` that references the pre-reorg path.)
- `trello-notes/` — Trello + LLM note-sorting automation (`merge_trello_cards.py`, `sort_trello_inbox.py`, `create_project_plan.py`, `llm_note_sorter.py`), the `trello` API client package, and a `prompts/` folder holding the LLM prompt and PDF-parsing instructions. Run `pip install -r scripts/trello-notes/requirements.txt`, then `cd scripts/trello-notes` before invoking any of these — some read files (like `prompt.txt`, `priorities.json`) relative to the current directory.

***

### Additional Resources

`setup.sh` automatically applies the trick from this article, so an activated conda environment persists into nvim/tmux child shells instead of resetting: it runs `conda init zsh`, wraps the resulting block in `if [[ -z "${CONDA_SHLVL}" ]]; then ... fi`, and adds the tmux-specific `source ~/miniconda3/etc/profile.d/conda.sh` line. Nothing to do by hand.

https://nielscautaerts.xyz/make-active-conda-environment-persist-in-neovim-terminal.html

I typically make project-specific aliases in the .zshrc which activate a conda env before starting nvim in a project directory, so this additional configuration helps avoid the need to activate conda environments again in child terminal processes.

Here is a nice tip about using ranger so that you can quit into the navigated directory:

https://github.com/ranger/ranger/issues/2679

***

