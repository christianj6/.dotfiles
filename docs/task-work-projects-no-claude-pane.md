# TASK: work projects get no claude pane — and fix the startup step's second bug

Owner rule, stated today in thor-voiceai: **work projects (anything under the tallence tree)
do not get a claude workhorse pane.** He shut the one there down. Reported by thor's
coordinator, which notes it will keep being told to open one every session until the
instructions carve work projects out.

## Bug 1 — the startup step contradicts the rule

`config/omp/context-files/APPEND_SYSTEM.md`, "Startup: the claude workhorse pane":

> The FIRST act of any new session, before anything else: open a herdr pane to the right of
> your own pane and start a claude workhorse in it.

No exception. So every work-project coordinator is instructed to create a pane the owner has
explicitly said he does not want.

**Fix:** scope it. For a **work project** (cwd under the tallence tree — the same test
`bro_stack.WORK_PATHS` uses, `/tallence/`), there is **no claude pane at all**; delegation is
`@task` subagents only. For a personal project, the step stands unchanged. Say the rule and
the reason, so a future reader does not "restore" the pane:

```
## Startup: the claude workhorse pane

The FIRST act of any new session, before anything else: open a herdr pane to the right of
your own pane and start a claude workhorse in it — **except in a work project** (cwd under
the tallence tree): the owner runs no claude workhorse there (2026-11-12) and delegation is
`@task` subagents only. Opening one there contradicts him and he will close it.
```

## Bug 2 — the documented split line fails in any `.conda-env` project

Line 38 says:

```
herdr pane split --current --direction right --cwd "$PWD" --no-focus
```

**That produces a pane running nvim, not a shell**, because `~/.zshrc` does

```zsh
[[ -n "${HERDR_ENV:-}" && -z "${NVIM:-}" && -z "${HERDR_NO_NVIM:-}" && -f "$PWD/.conda-env" ]] && exec nvim
```

and then `herdr agent start` refuses with `agent_pane_busy: pane … is not an available shell`.
**Proven live today**: `wD:pH` failed exactly this way; adding `--env HERDR_NO_NVIM=1` gave
`fg: zsh` and `agent start` then worked (`claude-v36-wdpj`).

**Fix:** the documented line must be

```
herdr pane split --current --direction right --cwd "$PWD" --no-focus --env HERDR_NO_NVIM=1
```

with one clause explaining why (a `.conda-env` project would otherwise `exec nvim` and the
pane is then not a shell). Same for any other documented split-then-start-a-claude recipe.

## Acceptance

1. `APPEND_SYSTEM.md`'s startup step names the work-project exception, and says delegation
   there is `@task` subagents only.
2. The documented `pane split` line includes `--env HERDR_NO_NVIM=1`, with the reason.
3. Grep the whole context-files tree for other instructions that tell an agent to open a
   claude pane unconditionally (e.g. the delegation rules, `rule://` files, `config/claude/`)
   and scope those too. Show the grep.
4. `config/claude/CLAUDE.md` is consistent: it describes claude as the dev workhorse — say
   plainly that a **work project has none**, so a work-project claude does not assume it
   should exist.
5. Nothing else about personal-project behaviour changes.
