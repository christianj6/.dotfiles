# Report: claude panes carry the harness config version (docs/task-claude-pane-version.md)

Committed locally, not pushed.

## Files changed

The two the task names:
- `config/herdr/plugins/claude-name/`: `names.py`, `test_names.py`, `herdr-plugin.toml`;
- `config/herdr/bin/workspace-rollout`.

**Outside the named files, and required:** the marker has to be written by claude itself at startup, which only a claude hook can do.
- `config/claude/hooks/claude-config-version.sh`: new;
- `config/claude/settings.json`: one more `SessionStart` hook command.

`config/omp/VERSION` is unchanged in meaning: one number for the whole harness.

## To make it live

1. **Restart the claude-name daemon** so it loads the new `names.py` (`pkill -f 'claude-name.*names.py'`). The next agent-status event relaunches it, as its `[[events]]` hook does.
2. **Restart claude panes** (`workspace-rollout`). Each new claude process writes its marker at startup. Until then every claude pane shows `-` and keeps the `claude-v2-…` fallback name.

## Startup hooks found

- **omp:** extension load. `omp-config-version.ts` runs when omp loads its extensions, at process start, and writes `/tmp/omp-config-versions/<pid>`. Unchanged.
- **claude: `SessionStart`.** It is already in use here: `settings.json` runs herdr's own `herdr-agent-state.sh session` on it. It fires on startup and on resume, and also on `/clear` and compaction within the same process.
  - So the hook writes its marker **only if absent**. The first `SessionStart` of a process (its start) sets the number, and later ones in the same process never rewrite it. That gives the same once-per-process semantics as omp's marker.
  - Its stdout would be added to the model's context, so the hook prints nothing.
- **How the hook finds the claude pid:** the hook runs as `claude → shell → script`, and it walks up its parents to the nearest process whose command is `claude`. I checked the ancestry from inside a claude pane: `zsh(27298) → claude(40911) → -zsh → herdr`.

No other mechanism was needed or invented.

## Behaviour

- **Marker:** `/tmp/claude-config-versions/<claude pid>` holds `config/omp/VERSION` as of process start.
- **Pane name** (claude-name): `claude-v<N>-<pane>` from the marker, e.g. `claude-v36-wdpc`, matching `omp-v36-wdp7`.
  - The pane's claude is found from herdr's `shell_pid` for the pane plus one `ps` table per tick: the top-most `claude` below that shell, directly or inside nvim's `:terminal`.
  - Two claudes under one shell count as ambiguous: no marker is used, and nothing is guessed.
- **No marker:** the name falls back to today's `claude-v<CLI major>-<pane>` (`claude-v2-wdpa`), a visibly different scale.
- **The CLI version is demoted to detail.** herdr's agent API has no detail or tooltip field (`herdr agent rename` sets only the name). So it is in the claude-name log line for each rename, and in `--list` as `(claude CLI 2.1.319)`, read from claude's own `~/.claude/sessions/<pid>.json` `version` field.
- **workspace-rollout:**
  - `claude_marker` now **reads** the marker and prints `-` without one. The old start-time-vs-VERSION-mtime inference (`~36` / `<36`) and the unused `VERSION_MTIME` are gone.
  - Up-to-date means marker == VERSION, the same test omp gets.
  - After restarting a claude, the verify loop now waits for **both** the resume and the new process's marker == VERSION. Before, it stopped at the resume, which would have been too early, since the hook writes just after start.
  - A claude with no marker is not up to date, so a rollout restarts it, and the new process then has a marker.

## `--list` before and after

(The cwd column shows the project name, written `<name>`: the real column prints the home-anchored checkout path, which stays out of this public repo.)

Before (the version was inferred from process start time, and the name showed the CLI major):
```
config/omp/VERSION = 36   (* = stale)
    wD:p9    omp-in-nvim     v35*    done     omp-v35-wdp9       <dotfiles>
    wD:pA    claude          v<36*   working  claude-v2-wdpa     <dotfiles>
    wD:p7    omp-in-nvim     v36     idle     omp-v36-wdp7       <prescient>
    wD:pC    claude          v~36    idle     claude-v2-wdpc     <prescient>
    wD:p5    omp-in-nvim     v36     idle     omp-v36-wdp5       <bro>
    wD:p6    claude          v~36    idle     claude-v2-wdp6     <bro>
    w5:p1D   omp-in-nvim     v36     idle     omp-v36-w5p1d      <heinzel>
    w5:p1A   claude          v~36    idle     claude-v2-w5p1a    <heinzel>
```

After, live. No claude has been started with the hook yet, so each is honestly unknowable:
```
    wD:pA    claude          -       working  claude-v2-wdpa     <dotfiles>  (claude CLI 2.1.318)
    wD:pC    claude          -       idle     claude-v2-wdpc     <prescient>  (claude CLI 2.1.319)
    wD:p6    claude          -       idle     claude-v2-wdp6     <bro>  (claude CLI 2.1.319)
    w5:p1A   claude          -       idle     claude-v2-w5p1a    <heinzel>  (claude CLI 2.1.319)
```

After, **demo**: markers written into a fresh `mktemp -d` scratch folder via the `CLAUDE_CONFIG_MARKERS` override, so the real `/tmp/claude-config-versions` was not touched. prescient's claude is marked 36 and bro's 35:
```
    wD:p9    omp-in-nvim     v35*    idle     omp-v35-wdp9       <dotfiles>
    wD:pA    claude          -       working  claude-v2-wdpa     <dotfiles>  (claude CLI 2.1.318)
    wD:p7    omp-in-nvim     v36     idle     omp-v36-wdp7       <prescient>
    wD:pC    claude          v36     idle     claude-v2-wdpc     <prescient>  (claude CLI 2.1.319)
    wD:p5    omp-in-nvim     v36     idle     omp-v36-wdp5       <bro>
    wD:p6    claude          v35*    idle     claude-v2-wdp6     <bro>  (claude CLI 2.1.319)
```

With the same demo markers, claude-name's naming computed against the live panes (a dry run, no rename):
```
wD:pA   pid=40911 marker=-   now=claude-v2-wdpa   -> claude-v2-wdpa
wD:pC   pid=14129 marker=36  now=claude-v2-wdpc   -> claude-v36-wdpc
wD:p6   pid=20406 marker=35  now=claude-v2-wdp6   -> claude-v35-wdp6
w5:p1A  pid=22778 marker=-   now=claude-v2-w5p1a  -> claude-v2-w5p1a
```

## Acceptance

| # | Check | Result |
|---|---|---|
| 1 | A fresh claude pane is named `claude-v<N>-<pane>`, N = VERSION at process start | **Shown in parts, not observed end to end.** I didn't start a new claude pane. The parts: the real hook, run under a real claude ancestor into a temp folder, writes VERSION for the right pid (`test_hook_writes_once_per_process`); the naming takes the marker over the CLI major (`test_marker_names…`); and the dry run on live panes gives `claude-v36-wdpc`. The first rollout of a claude pane is the end-to-end check. |
| 2 | The marker exists for a running pane; a stale pane keeps its old number | Write-once semantics tested: a pre-existing `35` is not rewritten by a later `SessionStart`. **No live marker exists yet,** because no claude has started since the hook was added. |
| 3 | `--list` shows a read version for claude, with `*` exactly as omps | PASS. See the demo: `v36`, and `v35*` for stale. The `~`/`<` inference is removed. |
| 4 | After a full rollout, every row shows the same N | **Not run.** It needs every claude pane restarted, which is the rollout's job. The rollout's success check now requires the new claude's marker to equal VERSION, so after a rollout the column reads the same N as the omps, or the restart reports FAILED. |
| 5 | No marker → the fallback name, and `-` in the column | PASS, live: all four claude panes today show `-` and keep `claude-v2-…`. Tested (`test_no_marker_falls_back…`: no file, garbage, no pid). |
| 6 | Existing claude-name tests pass, plus a marker test and a fallback test | PASS. The 5 existing tests are unchanged and pass. 4 new tests: marker naming, the no-marker fallback, pane→pid attribution (direct, in nvim, ambiguous, none), and the hook's write-once behaviour. |

## Notes

- **A false marker, removed.** While building the hook, I ran it once by hand from this pane, without the temp-folder override. That wrote `/tmp/claude-config-versions/40911` = 36 for this claude, which started Nov 5, before the bump to 36. The marker was false, so I removed that one file at once; the folder was otherwise empty. The hook test now always uses a temp folder (`CLAUDE_CONFIG_MARKERS`), and the demo used a fresh `mktemp -d` folder with nothing deleted.
- The `CLAUDE_CONFIG_MARKERS` override exists for tests and demos only. In normal use the hook, claude-name and workspace-rollout all use `/tmp/claude-config-versions`.
