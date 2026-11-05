# auto-ready: three breaks, and a fourth the spec's fix would miss

The coordinator found three independent reasons auto-ready never fires for role-targeted work. Verified against the live hub. I found a fourth while checking their remedy.

## The three confirmed breaks

**1. `agent` is `None` on all 142 items.** `tasks_of`'s `who()` returns `None`, so `tasks_for()` is empty for every project.

**2. `dest` is `None` on all 142 too.** The `agent:<name>` fallback in `who()` never applies either. Items carry only `project` and `target`.

**3. A state-vocabulary mismatch, independent of 1 and 2.**

```
OPEN_TASK  = ("open", "sent", "working")            # bro's LOCAL vocabulary
hub states = created, queued, working, ready, parked, undelivered, done
```
Only `working` overlaps. So a `queued` item is filtered out even with perfect matching — and a `ready` item too, which is worse: the thing we exist to detect is invisible.

## The fourth: `BRO_STATES` is not the translation you want

The coordinator's spec says "translate hub states via `BRO_STATES` before `OPEN_TASK`". Measured — it does not work:

```
queued  -> queued     in OPEN_TASK = False
ready   -> ready      in OPEN_TASK = False
parked  -> parked     in OPEN_TASK = False
```

`BRO_STATES` maps **bro's local vocabulary → prescient's display vocabulary** (`open`→`queued`, `sent`→`queued`, `noted`→`noted`). It does not map hub states into `OPEN_TASK`, because its codomain was never `OPEN_TASK`'s domain. Line 617 is the only `OPEN_TASK` use in the file; lines 1056 and 1112 use `BRO_STATES` for the *icon display*. **The two vocabularies are parallel and never meet.** Translating hub→BRO_STATES→OPEN_TASK is a no-op chain.

### What actually fixes break 3

Stop filtering by a state-name tuple. Define what "open" *means* once, against the hub:

```python
# the hub's own truth: an item is open unless it is closed
CLOSED_HUB = ("done",)
def is_open(t):
    return hub_state(t) not in CLOSED_HUB      # drop 'dropped' too: it arrives as done+resolution
```

or, minimally, widen `OPEN_TASK` to the hub's vocabulary and keep `BRO_STATES` purely for display. Either is fine; **what is not fine is a second vocabulary that has to be kept in step by hand** — that is the same duplication this whole day has been removing. My preference: one predicate reading the hub's states, with `BRO_STATES` demoted to a display map and a comment saying so.

**Careful with `ready`:** an item already `ready` must not be re-marked (it is not "open work" for auto-ready's purposes — it is already green). So the predicate for *auto-ready's candidates* is "open and not yet ready", which is a different set from "open" for display. Name them separately rather than bending one tuple.

## The rest of the fix

- **Readiness is a property of the project.** Match on `project` + `target`, never `agent`/`dest`.
- **Settle on the project's omp** (always present, per the owner: *"i will always use omp but optionally claude as a workhorse"*). Read the Claude's transcript when one exists — better evidence — the omp's when not. Never require Claude.
- Keep the false-green guards exactly as they are: settled, no other agent in the project busy, transcript tail is a finished answer, not started-by-the-agent.
- Touch neither "only the owner drops" nor any provenance rule.

## Acceptance

1. **No Claude.** A `coordinator`-targeted item reaches `ready` after the omp settles post-answer.
2. **Claude present.** Same, and the Claude's transcript is the one read for the tail check (assert which file was read, not just the outcome).
3. **Break 3, explicitly.** A `queued` item is a candidate; a `ready` item is not re-marked; a `done` item is never a candidate. Show the predicate's output for each hub state, not just one happy path.
4. **The invariant that ties it to the icon:** for any project, if any item is `ready`, the project's status is `ready` — this needs prescient's bug-1 fix too, and both halves must be green before the owner sees green.
5. History-only project still `idle` / "nothing open".

## Ownership

The plugin is a dotfiles file. The coordinator has accepted it as mine to implement or route, and will review the diff and verify cases 1–2 against the live hub. I will implement it, since it is the repo I own.
