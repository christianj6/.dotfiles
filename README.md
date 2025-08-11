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

