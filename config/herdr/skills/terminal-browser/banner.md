
## Machine notes (added by setup.sh) — read the companion skill first

On this machine ALWAYS also read the companion skill `terminal-browser-quirks`
(installed next to this file) BEFORE driving a browser: it carries the
standard workflow and the local corrections. Short version:

1. `terminal-browser open <url> --split right` puts the page beside the human
   (`--split down` for tall/narrow panes; a local html path is a first-class
   url — write a page and render it instead of pasting HTML into chat).
2. `terminal-browser ls` lists browsers/tabs; `terminal-browser ls --json`
   also gives `.browsers[].cdpPort`.
3. `terminal-browser action -- <cmd>` FAILS on this machine ("could not
   connect agent-browser") — drive the browser with the bundled CLI over
   IPv4 instead:

       AB=~/.local/share/terminal-browser/app/agent-browser/bin/agent-browser
       $AB connect http://127.0.0.1:<cdpPort>   # URL form, not bare port
       $AB snapshot                             # a11y tree with @refs
       $AB click @ref / fill @ref "text" / eval "js"
       $AB done                                 # when finished acting

Retire this banner (and the companion skill) once a terminal-browser upgrade
fixes the wrapper (v0.8.0 tested 2026-09-07).
