# Request from the .dotfiles coordinator: "N hidden" chip for the agent column

Owner request, relayed per `rule://coordinator-network` (omp ↔ omp across projects). Prescient's dashboard is your repo; this is a UI change only.

## Problem
Hiding an agent icon (`hide until active`) is currently **one-way and unreachable**:

- `agVisible()` (`prescient/gantt/static/index.html` ~line 9157) computes the hidden groups as `vis.out`, but **nothing renders them** — the only reference is an internal test assertion.
- An icon comes back only via `newWork` (`agTaskSig(g).some(s => !e.tasks.includes(s))`) or `e.quiet && !agQuiet(g)`.
- Two stuck states exist: (a) the hidden map's key no longer matches any board group (e.g. hidden while the agent's cwd resolved to a worktree), where `if (!g) { keep[k] = e; continue; }` keeps it hidden **forever**; (b) a new task whose signature equals the snapshot (`id=state` unchanged) does not count as `newWork`, and a group hidden while active (`quiet: false`) can't satisfy the second condition either.

Owner hit this live: hid the thor-voiceai icon, then manually gave the agent a new task, and it still never came back. Only `localStorage.removeItem('lw.agHidden')` recovered it.

## The ask
Add a **"N hidden" chip** in the agent column that restores hidden icons on click (click → clear those entries → re-render). **Keep it really subtle — the owner explicitly does not want visual clutter.**

Design constraints from the owner's taste (please respect these rather than making a normal button):
- Invisible when nothing is hidden (`N == 0` → render nothing at all).
- One short text chip at the very bottom of the agent column, in the existing muted/quiet style (`class="quiet"`-like, `--muted` colour, small font, no border/background fill) — e.g. `2 hidden`.
- Hovering reveals what they are (title attribute listing project names); clicking restores all of them.
- No counts badge, no icon, no confirmation dialog, no animation.
- Must not shift the layout of the visible icons (place it after the column, not inline among them).

## Also please fix the two stuck states (cheap, same file)
1. Drop hidden entries whose group no longer exists instead of keeping them forever (`if (!g) { keep[k] = e; continue; }` → do not keep; or prune on a timer).
2. Treat a **state change** on an existing task as work too: `newWork` currently compares `source:id=state` strings, so a task going `sent → working` does count (state is in the signature) — verify that; if not, include the state transition explicitly.

## Acceptance
- With nothing hidden: column renders exactly as today (no new element).
- Hide one icon → a single muted `1 hidden` line appears at the column's end; hovering names it; clicking restores the icon and the chip disappears.
- The two stuck states above reproduce as fixed.
- Existing tests still pass; add a case for the chip's hidden-when-zero behaviour.
