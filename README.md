# .dotfiles
Miscellaneous configuration files for a reproducible workspace.

***

### Setup

```
git clone ...
cd .dotfiles/
bash ./setup.sh
conda init
nvim
```

***

### Instructions for Setting Up Mac 

1. Administration Programs 
    - Sunsama 
    - 1Password 
    - Arc Browser
        - Vimium Extension 
        - 1Password Extension 
2. Terminal Workspace
    - Pull .dotfiles Repository
    - Run setup.sh
3. Additional Programs 
    - ChatGPT 
    - Docker Desktop 
    - Draw.io 
    - Leader Key 
    - Terraform

Miscellaneous Programs
- Sublime Merge 
- Ollama 

***

### Utility Scripts

The /scripts directory contains some random utility scripts for:
- Creating a Python project template.
- Managing Trello cards.

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

***

### TODO

- [ ] Migrate to stow for symlink management.
- [ ] Windows and Linux setup compatibility.

***
