# Claude pane verification: auto mode and global context

Run 2026-11-02 on Claude Code 2.1.316 and herdr 0.9.5, in a throwaway workspace
that was closed afterwards. The pane ran plain `claude`, with no flags, in a new
directory under `$HOME`.

## Result

| Check | Result |
| --- | --- |
| Starts in auto mode without shift+tab | Pass |
| Has the global context | Pass |
| No stall on the directory-trust prompt | Fails on first run in a new directory; passes after that |
| SessionStart hook still reports to herdr | Pass |

## Commands

    herdr workspace create --cwd "$HOME" --label automode-scratch --no-focus
    herdr pane run <pane> "cd ~/automode-scratch && claude"

## 1. Auto mode

Footer after the trust answer, with no other keys pressed:

    ❯ Try "edit <filepath> to..."
      ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents

The session transcript also records `permissionMode= auto`.

`permissions.defaultMode: "auto"` is the key that works. `autoMode` only
customizes the classifier.

## 2. Global context

    user: in one line, what is your role and how do specs reach you?
    assistant: I'm the dev workhorse for this project, working under the omp
    coordinator agent, and specs reach me as a file path plus one line.

## 3. Directory trust

First run in the new directory:

     Accessing workspace:
     ~/automode-scratch
     Quick safety check: Is this a project you created or one you trust?
     ❯ No, exit
       Yes, I trust this folder
     Enter to confirm · Esc to cancel

herdr reported `status: unknown`, so status alone does not reveal this stall.
Nothing in `settings.json` covers it: trust is recorded per directory.

Mitigation: answer the prompt for that one directory (`down`, then `enter`), as
the workstreams skill now says. No blanket pre-approval was added. The default
option exits claude, so an unattended Enter closes the pane.

Restart in the same directory, with no input:

    $ claude
    ❯ Try "edit <filepath> to..."
      ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents

The screen held no trust prompt. A write inside the project then ran without a
dialog (`note.txt`, `xxd`: `6f6b 0a`).

## 4. Hook and plugin

Fresh pane, from `herdr agent get`:

    status idle session {'agent': 'claude', 'kind': 'id', 'source': 'herdr:claude', 'value': '348f23ad-...'}

`herdr integration status` went from `outdated (v8 < v11)` to `current (v11)`.

## What failed, and why

- **`herdr integration install` writes through symlinks.** Run against linked
  files in a throwaway `$HOME`, it appended a second SessionStart entry with a
  machine-absolute path to the versioned settings, and rewrote the versioned
  hook. `setup.sh` therefore removes the links, lets the install write real
  files, then links back. Two runs of that block left the repo unchanged.
- **Claude writes through the symlink too.** `/effort high` added a
  `modelSettings` key to `config/claude/settings.json`. The link survived, but
  in-app settings changes appear as repo diffs. Review them before committing;
  the test key was removed.

## Not tested

- `skipAutoPermissionPrompt: true`. The opt-in dialog never appeared on this
  machine, so nothing shows the key is needed or that it works on a new one.
- Resumed sessions, including `workspace-rollout` restarts. Only new sessions
  were checked.
- Running a full `setup.sh`. Only its claude block was run, in a throwaway
  `$HOME`.
