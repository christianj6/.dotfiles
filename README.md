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
conda init
nvim
```
You will probably also need to install various packages and/or configure a Nerd Font, but the above will get you 95%. After this setup, it is a good idea to put some aliases etc. in the .zshrc.

`setup.sh` is idempotent — re-run it any time (e.g. after pulling updates) to pick up new packages and symlinks; it skips work that's already done.

***

### Utility Scripts

The /scripts directory:
- `new-python-project.sh` — scaffold a new Python project (conda env, pre-commit, git init).
- `devcontainers/` — `setup-claude-devcontainer.sh` / `setup-opencode-devcontainer.sh` copy a devcontainer config into any project and start it. `setup.sh` symlinks these into `~/.local/bin` as `claude-setup` / `opencode-setup`, and keeps the matching `claude` / `opencode` shell functions in your `~/.zshrc` current inside a marked block (`# >>> dotfiles devcontainer helpers >>>` / `<<<`) — it never touches anything else in that file, and backs it up (`~/.zshrc.bak.<timestamp>`) before any change. (`scripts/setup-claude-devcontainer.sh` / `setup-opencode-devcontainer.sh` also still exist as symlinks into `devcontainers/`, for any already-deployed `.zshrc` that references the pre-reorg path.)
- `trello-notes/` — Trello + LLM note-sorting automation (`merge_trello_cards.py`, `sort_trello_inbox.py`, `create_project_plan.py`, `llm_note_sorter.py`), the `trello` API client package, and a `prompts/` folder holding the LLM prompt and PDF-parsing instructions. Run `pip install -r scripts/trello-notes/requirements.txt`, then `cd scripts/trello-notes` before invoking any of these — some read files (like `prompt.txt`, `priorities.json`) relative to the current directory.

***

### Additional Resources

Here is a nice article which explains how to configure the .zshrc so that activated conda environments are used in nvim child processes. I typically make project-specific aliases in the .zshrc which activate a conda env before starting nvim in a project directory, so this additional configuration helps avoid the need to activate conda environments again in child terminal processes.

https://nielscautaerts.xyz/make-active-conda-environment-persist-in-neovim-terminal.html

The main idea is to insert the following snippet around the conda init logic:
```
if [[ -z "${CONDA_SHLVL}" ]]; then
  # >>> conda initialize >>>
  ...
  # <<< conda initialize <<<
fi
```

Here is a nice tip about using ranger so that you can quit into the navigated directory:

https://github.com/ranger/ranger/issues/2679

***

