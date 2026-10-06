# terminal-browser performance analysis — darwin arm64, v0.8.0 (static, no launch)

Investigated 2026-10-06 by BrowserPerfScout (read-only; `terminal-browser`/`agent-browser` never executed). Evidence path prefix: `~/.local/share/terminal-browser/app` = `APP`. Integration disabled 2026-10-05 (`TB_DISABLED=1` in setup.sh) pending this analysis.

## 1. Architecture: what actually runs when an agent invokes it

**Invocation chain (every CLI call):**
1. `~/.local/bin/terminal-browser` — 1-line sh wrapper: `exec .../app/bin/terminal-browser "$@"`.
2. `APP/bin/terminal-browser` — sh script that sets `TERMINAL_BROWSER_DIST_ROOT`, **`ELECTRON_RUN_AS_NODE=1`**, `NATIVE_SCROLL_HELPER`, then `exec`s the full Electron GUI binary **as plain Node** to run `APP/cli/dist/main.js` (23,714-line esbuild bundle, CommonJS; per-process Node boot each time — no CLI daemon).
3. The Electron **daemon** is a second process: `browser/dist/main.js` (39,912 lines) run as a real GUI app (`browserLaunchCommand`, cli/dist/main.js:23068-23096 — `/bin/sh -c "exec <Electron.app binary> <main.js> --daemon 2>> stderr.log"`). Clients reach it over a Unix socket `daemon.sock` (`DAEMON_SOCKET`, cli:75-77).
4. **Browser sessions** live inside the daemon process: Electron `BrowserWindow`s with `offscreen: { useSharedTexture: true, sharedTexturePixelFormat: "argb" }` (browser/dist/main.js:30858-30875, 31063-31067). Pixels never hit a real window; each frame is presented to a terminal surface with damage rects (presentPaint/presentTexture/presentShmFrame, browser:30910-30959) and written as **kitty-graphics escape-sequence bytes into the pane's tty** (`term.write`/`bytes` per-frame counters, browser:27184). The visible "browser" is the terminal rendering those frames.
5. CDP: the daemon picks a free IPv4 port and appends `--remote-debugging-port` to Chromium (browser:39831-39842). agent-browser (bundled Go CLI at `APP/agent-browser/bin/agent-browser`) talks to it directly for snapshots/eval.

**Per-`open --split right` pipeline** (cli:23522-23550, 23359-23380, 23127-23153, 21518-21545): parent CLI boot → `ensureSetup` (version marker) → `tryAdopt` (reuse existing browser) → `currentTerminal()` = herdr adapter: read `~/.config/herdr/config.toml`, then **kitty-graphics probe with 500ms timeout** (`probeGraphics`, cli:20296-20340) → `ownTtyPath()` (execFileSync `tty`) → `callerTty()` (**up to 30 sequential `ps -o ppid=,tty=` execs** walking ancestors, cli:20255-20274) → `herdr pane split` + run child CLI in new pane → **poll `listInstances` every 250ms up to 20s** → child CLI boot (probe again in new pane) → `daemonSocket()`: if absent, **spawn full Electron daemon and poll every 200ms up to 15s** → daemon `createSession` (offscreen window + CDP port).

**Agent snapshot path:** `ls --json` (CLI boot + probe + herdr `pane list` + **one `herdr pane process-info` subprocess per pane** + `ps` TTY map, cli:21043-21064) → bundled agent-browser `connect http://127.0.0.1:<cdpPort>` → CDP a11y snapshot. The wrapper's own `terminal-browser action --` instead does **synchronous `spawnSync(agentBrowser, [--cdp <bare port>, ...])`** (cli:21666-21713), which fails on this machine (IPv6/localhost vs IPv4-only CDP listener — documented in terminal-browser-quirks SKILL.md, live-tested 2026-09-07) after burning a full agent-browser process + reconnect attempt per try; the exact failure string `could not connect agent-browser to terminal browser <key> on port <port>` is cli:21708.

## 2. Ranked root-cause hypotheses

1. **Cold Electron daemon boot is paid repeatedly** — HIGH. `IDLE_EXIT_MS = 15000`: the daemon self-exits 15s after the last session closes (browser:39629, 39652-53). Any new `open` after that spawns a full Electron app detached and polls the socket 200ms up to 15s (cli:23139-23153). Agent sessions that close the browser between steps re-pay the heaviest cost every time.
2. **`open --split` end-to-end latency is a serial chain of ~7 stages with poll-granularity slack** — HIGH. Parent CLI boot → probe (≤500ms) → ps-walk → herdr split → child CLI boot → probe again → daemon boot (if idle-expired) → 250ms-poll registration wait (cli:23367-23379). No stage is parallel; worst case ≈ 15s daemon budget + 20s registration budget.
3. **Every CLI call maps/loads the ~307MB Electron bundle as Node** — MEDIUM-HIGH. `ELECTRON_RUN_AS_NODE=1` (bin/terminal-browser) still launches the Electron Mach-O binary; plus parsing the 23.7k-line CLI bundle. Typical overhead vs a small native/node binary: hundreds of ms per call, multiplied by the 2-4 CLI invocations per workflow (open, ls, action).
4. **Fixed 500ms graphics probe on terminal resolution, twice per `open`** — MEDIUM. `PROBE_TIMEOUT_MS = 500` (cli:20297); skipped only with `TERMINAL_BROWSER_SKIP_GRAPHICS_CHECK=1` (cli:21541). Ghostty+herdr with kitty graphics enabled answers fast, but any pane that swallows the query pays 500ms ×2 per open, plus `herdr prepare()` config read/possible rewrite + `herdr server reload-config` (cli:21031-21040).
5. **herdr pane discovery subprocess fan-out** — MEDIUM. `listPanes` = `herdr pane list` + N× `herdr pane process-info` + `ps -o pid=,tty=` (cli:21043-21064), and cwd-marker matching retries with `sleep(120)` ×2 attempts (cli:20882-20888). Runs for `ls`, adopt checks, `getCurrentPane`. Cost scales with pane count; each herdr call is itself a CLI spawn.
6. **`action --` CDP mismatch burns a process + retry per attempt** — MEDIUM (workflow cost, already mitigated by the quirks skill). Bare-port `--cdp` fails on the IPv4-only listener; wrapper then errors (cli:21700-21708). Agents must hand-drive agent-browser over `http://127.0.0.1`.
7. **Continuous offscreen repaint → escape-byte traffic to the pane tty** — MEDIUM on heavy pages. Frames are presented with damage rects and `bytes` escape sequences per frame (browser:27184, 30910-30959); animated pages keep the paint/encode/write path and ghostty's decoder busy, competing with agent work on a loaded machine.
8. **`callerTty` sequential `ps` per ancestor hop (≤30)** — LOW-MEDIUM; in herdr the process chain is shallow but each hop is a ~10ms execFileSync (cli:20255-20274).
9. **Stale-daemon handshake: `sleep(700)` + double reconnect on build-stamp mismatch** — LOW (cli:23192-23204).
10. **Machine load context (not tool-caused)** — dozens of headless Google Chrome helper trees from omp daemons (`--user-data-dir=.../.omp/run/daemons/<id>/omp.browser.headless.profile`, alive since Sep 16-30), plus Slack/Sunsama/Steam/VS Code(AppTranslocation). Background CPU/GPU/memory pressure amplifies everything above.

## 3. Cheap mitigations (no tool removal)

- `export TERMINAL_BROWSER_SKIP_GRAPHICS_CHECK=1` for agent shells — kills the 500ms probe per resolution (cli:21541).
- Keep one browser session alive across an agent's steps (don't `$AB close` mid-session) so the 15s idle exit never triggers; open the browser once, cache `cdpPort` from `ls --json`, drive agent-browser over `http://127.0.0.1:<cdpPort>`.
- Never use `terminal-browser action --` (documented); the quirks-skill workflow is the fast path.
- Prefer `open` in the current pane (`openHere`) over `--split` when a pane already exists — skips herdr split + child CLI + registration poll.
- Upgrade terminal-browser past v0.8.0 (wrapper/CDP fixes); retire banner + quirks skill once fixed.
- Close orphaned herdr panes per the quirks skill so pane fan-out (`process-info` per pane) stays small.
- Unrelated but recommended for machine load: reap stale omp headless-Chrome daemon trees (owner decision; do NOT kill without owner approval).

## 4. Currently running / should be stopped

- **Nothing** terminal-browser/agent-browser related is running (ps + lsof, Main's shell, before AND after snapshots) — nothing to stop for this tool.
- Listeners present but unrelated: node on 127.0.0.1:3000, herdr-ish 8177-8179, 55948, 35212 (ports 18789/18791/18792) — inspected only, never connected.
- omp headless Chrome trees (54 helpers at after-snapshot) are omp's own browser tool — separate cleanup decision.

## 5. Process snapshots (from Main's shell; the scout ran none)

**BEFORE:** no terminal-browser/agent-browser processes; no agent-browser/node/Electron/terminal-browser TCP listeners; no runtime state in `~/.local/share/terminal-browser` (bundle only), no `~/Library/Caches` entries.
**AFTER:** unchanged for this tool — zero terminal-browser/agent-browser processes/listeners; 54 Chrome helpers (omp daemons), Steam/1Password/VS Code/Slack/Sunsama as listed above.
