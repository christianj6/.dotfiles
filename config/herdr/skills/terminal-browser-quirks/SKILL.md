---
name: terminal-browser-quirks
description: Local working notes for terminal-browser (v0.8.0) on this machine — the working CDP path when `terminal-browser action --` fails to connect, port discovery, and the split-pane + click recipe. Read whenever terminal-browser's own skill tells you to run a command that errors with "could not connect agent-browser".
---

# terminal-browser quirks (this machine)

Live-tested 2026-09-07 against terminal-browser v0.8.0. The upstream skill in
`~/.local/share/terminal-browser/app/skills/default/terminal-browser/` is the
command reference; this file only carries what breaks locally and the verified
workaround. Never edit the upstream file — `terminal-browser upgrade`
overwrites it.

## The failure you will hit

`terminal-browser action -- <cmd>` (and any `--browser/--tab` selector form)
fails here with:

    terminal-browser: could not connect agent-browser to terminal browser
    <key> on port <port>

Its wrapper resolves the CDP port as a bare port number; on this machine that
connection fails (IPv6/localhost resolution trap — `::1` is refused, the
listener is IPv4-only), while `127.0.0.1` works. Two subcommands
(`terminal-browser action done` and the `ls` listing) use a different path and
DO work — the failure is specific to the agent-browser passthrough.

## The working path (verified end-to-end)

1. Find the CDP port:

       terminal-browser ls --json      # .browsers[].cdpPort, .browsers[].key
       terminal-browser ls             # human list; browser key + tabs + tab ids

2. Drive the browser with the bundled agent-browser CLI over IPv4:

       AB=~/.local/share/terminal-browser/app/agent-browser/bin/agent-browser
       $AB connect http://127.0.0.1:<cdpPort>     # URL form required; bare port errors
       $AB snapshot                               # a11y tree with refs (@e2, ...)
       $AB click @e2
       $AB eval "location.href"
       $AB fill @e3 "text"
       $AB done                                   # clears the agent-acting indicator

   Repeat `connect` if the browser was restarted; it prints "[agent-browser]
   relaunched browser" when it re-attaches. When done driving a page the human
   is looking at, run `$AB done` — same etiquette as the upstream skill.

## Recipes

Open side-by-side with the conversation (renders via kitty graphics in
ghostty/herdr; both already enabled here):

    terminal-browser open <url|path.html|localhost:port> --split right

`--split down` for tall/narrow panes; `--size 0.2..0.95` for width. A local
html path is a first-class URL — write a page, open it, screenshot-by-browser
instead of dumping HTML into the chat.

## Provenance

- v0.8.0 wrapper bug reproduced 3× and bypassed end-to-end: connect over
  IPv4 → snapshot → click @e2 → navigated example.com → iana.org.
- `127.0.0.1:PORT` (bare port form) is REJECTED by agent-browser's connect —
  use the `http://` URL form.
- If a future terminal-browser upgrade fixes the wrapper, retire this skill.
