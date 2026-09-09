---
name: terminal-browser-quirks
description: Companion to the terminal-browser skill — read BOTH. Carries the standard usage workflow on this machine (open --split right → ls → agent-browser connect → snapshot/act → done → close the pane), the working CDP path when `terminal-browser action --` fails ("could not connect agent-browser"), and the split-pane + click recipe. Read this whenever you touch terminal-browser.
---

# terminal-browser quirks (this machine)

This is the **companion to the `terminal-browser` skill** — read both. The
other skill is the full command reference (canonical copy managed by
terminal-browser, installed beside this one); this file is the standard
workflow on this machine plus the local corrections. Live-tested 2026-09-07
against terminal-browser v0.8.0. Never edit the canonical skill file —
`terminal-browser upgrade` overwrites it (and setup.sh re-syncs the installed
copies from it on every run).

## Standard workflow (start here)

1. **Open the page beside the conversation** — right split for wide panes:

       terminal-browser open <url|file.html|localhost:port> --split right

   `--split down` for tall/narrow panes, `--size 0.2..0.95` for width. A
   local html path is a first-class url — write a page and render it instead
   of pasting HTML into the chat. Rendering goes through kitty graphics
   (ghostty/herdr already have it enabled on this machine).

2. **List browsers and tabs** (also grab the CDP port):

       terminal-browser ls            # human list: browser key, tabs, tab ids
       terminal-browser ls --json     # .browsers[].key, .browsers[].cdpPort,
                                      # .browsers[].pane (hosting herdr pane)

3. **Connect the bundled driver CLI over IPv4** — NOT
   `terminal-browser action --` (see below for why):

       AB=~/.local/share/terminal-browser/app/agent-browser/bin/agent-browser
       $AB connect http://127.0.0.1:<cdpPort>

   URL form is required; the bare `127.0.0.1:<cdpPort>` port form is
   rejected. It prints "[agent-browser] relaunched browser" when
   re-attaching after a browser restart.

4. **Drive, then finish**:

       $AB snapshot                    # a11y tree with @refs (@e2, ...)
       $AB click @e2 / fill @e3 "text" / eval "location.href"
       $AB done                        # clears the agent-acting indicator

   `done` at the end is etiquette — the human sees a live "agent is acting"
   indicator until it expires or is cleared.

5. **Close out BOTH the browser and its herdr pane.** Closing the browser
   (`$AB close`) does NOT close the pane it was split into under herdr —
   the pane is left behind as an orphaned empty shell with its cwd reset
   to `$HOME` (verified live 2026-09-07: browser closed, pane `w6:pG`
   remained with cwd=$HOME, agent=unknown). The hosting pane id comes
   straight from `ls --json` — no manual pane hunt needed:

       terminal-browser ls --json     # .browsers[].pane = {"tab": "w6:t3", "pane": "w6:pG"}
       herdr pane close w6:pG         # browser first or pane first — both orders work

   Do this whenever the session with the browser is over — otherwise every
   terminal-browser session leaves a stray pane in the human's tab. (If the
   browser already exited, `ls --json` can no longer tell you the pane:
   fall back to `herdr pane list --workspace <ws>` and look for the
   cwd-reverted-to-$HOME no-agent pane in the same tab — that signature is
   unambiguous.)

## Why step 3 is not `terminal-browser action --`

`terminal-browser action -- <cmd>` (and its `--browser/--tab` selector
forms) fails on this machine with:

    terminal-browser: could not connect agent-browser to terminal browser
    <key> on port <port>

The wrapper hands agent-browser the CDP port as a bare port number; on this
box that connection fails (IPv6/localhost resolution trap — `::1` refused,
the listener is IPv4-only) while `127.0.0.1` works. Two subcommands take a
different path and DO work (`terminal-browser action done`, the `ls`
listing) — the failure is specific to the agent-browser passthrough. If a
future upgrade fixes the wrapper, retire this skill.
