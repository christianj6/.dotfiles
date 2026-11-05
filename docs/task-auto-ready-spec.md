# TASK: auto-ready — four breaks, one fix

Repo: ~/.dotfiles. File: config/herdr/plugins/lifeview-fallback/lifeview.py (and its test file next to it).
Full reasoning: docs/auto-ready-four-breaks.md — READ IT FIRST. Hub task: tk-8c1fa7742905.

## Symptom (owner)
prescient goes green when work is ready for review; other projects go amber then grey — never green. "as long as a project has an omp pane it should still work the same. i will always use omp but optionally claude as a workhorse."

## The four breaks (all verified against the live hub, 142 items)
1. `agent` is None on ALL items -> `tasks_of`/`who()` never matches -> `tasks_for` always empty.
2. `dest` is None on ALL items -> the `agent:<name>` fallback never applies either.
3. State vocabulary mismatch: `OPEN_TASK = ("open","sent","working")` is bro's LOCAL vocabulary; hub says created/queued/working/ready/parked/undelivered/done. Only `working` overlaps. `ready` is OUTSIDE the tuple.
4. `BRO_STATES` is NOT the translation for #3. It maps bro-local -> prescient DISPLAY vocabulary. Measured: queued->queued, ready->ready, parked->parked, all still outside OPEN_TASK. OPEN_TASK has exactly one use (line 617); BRO_STATES feeds display (1056, 1112). Do not chain them.

## Required changes
A. **Readiness is a property of the PROJECT.** Match candidates on `project` + `target`, never on `agent` or `dest`. Delete the agent-keyed path from the auto-ready decision (leave `tasks_of` alone if other callers use it — check first with grep, and say in your report who else uses it).
B. **One predicate over hub states**, replacing the OPEN_TASK filter for auto-ready:
   - candidates = items whose hub state is OPEN AND not already `ready`. Name this set explicitly (e.g. `ready_candidates`) because "open" for display and "open and not yet ready" for auto-ready are DIFFERENT sets. A `ready` item must never be re-marked; a `done` (or done+dropped) item is never a candidate.
   - Keep `BRO_STATES` ONLY for display, and add a one-line comment saying that, so the next reader cannot chain them again.
C. **Settle on the project's omp** (always present). When a Claude exists in the project and it is the agent that did the work, read the CLAUDE's transcript for the tail check (better evidence); otherwise read the omp's. NEVER require a Claude.
D. **Do not touch**: the false-green guards (settled / no other agent busy / transcript tail is a finished answer / not started-by-the-agent), "only the owner drops", or any provenance rule.

## Acceptance — show, do not describe
1. No Claude in the project: a `coordinator`-targeted item becomes `ready` after the omp settles post-answer.
2. Claude present: same outcome, AND the Claude's transcript is the file read for the tail check — assert WHICH path was read, not just the result.
3. Break 3, explicitly: print the predicate's verdict for EVERY hub state (created, queued, working, ready, parked, undelivered, done) — a table, not one happy path.
4. Invariant: for any project, if any item is `ready`, the project's status is `ready`. (Needs prescient's status() fix too; that half is routed separately — test your half alone and say so.)
5. History-only project still `idle` / "nothing open".
6. Existing plugin tests pass; do not weaken any assertion to make it pass.

## Rules
- Run the plugin's own test file. No formatters, no project-wide suites.
- Do NOT push. Commit locally with a message citing tk-8c1fa7742905 and the four breaks.
- Report: what changed, what you ran, the per-state table, and anything you chose not to do and why.
