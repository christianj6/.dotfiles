# Report: the plugin's hub writes now carry the launch token (docs/task-plugin-write-token.md)

Committed locally, not pushed. **Live:** I stopped the stale daemon (it started at 12:30, before this fix). herdr's event hook relaunched it on the new code, and it has opened real auto-tasks since.

## Change (`config/herdr/plugins/lifeview-fallback/lifeview.py`)

- **`hub_write(body, what)`** is now the only way the plugin writes to the hub. It sends `X-Prescient-Token`, and both hub writes go through it: the auto-task create and the auto-ready start/ready. A test fails if a second `http_json(HUB_URL + "/api/tasks", <body>)` appears.
- **`hub_token()`** reads the token file **on every call**, never cached. The file is `.server-token` for port 8765 and `.server-token-<port>` for any other port; the port comes from `HUB_URL`. The folder is `PRESCIENT_DATA_DIR`, taken from the env or from the plugin's local config file outside the repo, because herdr starts the daemon without our env. I added that key to the local config.
- **Refusals are logged once per shape** (what + status + error + token problem), e.g. `hub write refused: auto-task create: 403 a write needs this launch's token …`.
  - A missing token file adds a different reason that says what to fix: `[no token: <path> unreadable (FileNotFoundError); is the hub running from that data dir?]`.
  - An unset data dir adds `PRESCIENT_DATA_DIR is not set (put … in <config>)`.
  - `auto_task`'s failure line used to blame "bro CLI" even in hub mode. It now says `NOT opened: refused <reason>`.
- **`http_json`** takes an optional `headers` and `outcome` (status + the hub's `error` text). Reads are unchanged: still `None` on any failure.
- **`--explain`:**
  - a header line `hub write token: found (.server-token)` or the problem;
  - per agent, `auto-task: would open '<title>' - <why>` (instead of the bare why);
  - `open: ok <id>` / `open: refused <error>` / `open: skipped <why>`, read from `/tmp/lifeview-fallback.hub-last.json`, which the daemon writes on every attempt. explain runs in a separate process, so it reads the daemon's last attempt from that file.
- **The token never appears anywhere:** grepping for the live token in the daemon log, the outcome file and the `--explain` output gives 0 / 0 / 0.

## Acceptance

1. **A real `open_task` returns an id:** `tk-03633b4a4f71`, created for claude-v2-wdpa through `lv.open_task` on the live hub.
   ```
   tk-03633b4a4f71  queued      dotfiles/coordinator auto: plugin write-token acceptance (lifeview open_task, live)  nudged: ok
   ```
   The hub has it with `project=dotfiles, target=coordinator, origin=harness`. The relaunched daemon then opened **`tk-e9d0ee9c7714`** for omp-v36-wdp7 (prescient) on its own: the first auto-task since the gate landed.
2. **Live refusals:**
   - **Wrong token, two creates:** both refused 403, with **one** log line.
   - **No token file:** a different line naming the missing file.
   - Neither created an item: 0 items matching the text.
3. **`--explain` on live panes:**
   ```
   hub write token: found (.server-token)
   omp-v36-wdp7 …  auto-task: would open 'auto: I have the four open items mapped. …' - work session: 8 tool calls, 283s, no task covering it
   (after the relaunch)  open: ok tk-e9d0ee9c7714  (35s ago, 'auto: Okay, have Claude close the remaining open points and…')
   ```
   **How to read `open:`.** It is a record the daemon writes to `/tmp/lifeview-fallback.hub-last.json` on each attempt, per agent, starting with this fix. A pane whose agent has had no attempt since then shows `open: no attempt recorded …` even while other panes show ids. That line means "nothing tried for this agent yet", **not** "opens never happen". The coordinator saw exactly that split: one pane with `open: ok tk-03633b4a4f71`, another with the empty line.
4. **Tests: 131 OK.** The 6 new ones run against a real local HTTP hub that enforces the token:
   - a write with the token succeeds and records `ok`;
   - the token is read per call: a stale file is refused, and the rewritten file succeeds;
   - a wrong token is refused and logged once, with the token absent from logs;
   - a write without a token file sends no header and reports the refusal, naming the file;
   - an unset data dir says how to set it;
   - there is only one hub write path.

   The existing fakes now accept `**kw`. Tests point `HUB_LAST_PATH` and `PRESCIENT_DATA_DIR` at a temp folder, so they never touch live state.
5. **No token in any log or explain line.** Checked live (above) and in a test.

## Reported, not resolved

- **A second writer used this uncommitted code. Resolved: it was the coordinator.** `tk-5441ae6cc5ec` ("auto: PROBE: token acceptance check - safe to drop", project heinzel) was the coordinator's own probe of the open path, created 14:25:16 through the working tree and dropped 14 s later. I first guessed heinzel's coordinator; that guess was wrong. heinzel's coordinator only read the item and took it for its own card (a false pass, since corrected by the coordinator). The probe did write omp-v36-w5p1d's entry in the outcome file at the same time as my runs. Nothing was lost, but it is the two-writers-one-tree case, so it was reported rather than cleaned up.
- **Not fixed, out of scope:** `prompt_provenance` returned `None` for this turn, whose prompt was a pure `<pasted_content>` message. That is why my acceptance item has origin `harness`. By the same rule, `autotask_check` refuses such a turn ("no prompt to attribute"), so a paste-only request from the owner gets no auto-card.
- The old daemon's log shows the bug as it happened: `14:22:25 auto-task for omp-v36-wdp9 failed (bro CLI: …)`. The real cause was a 403.
