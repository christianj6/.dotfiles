# Final read: bro's 16 unpushed commits (2026-11-03)

## URGENT — the index corruption was mine, and it is fixed

My privacy-hook probe used `export GIT_INDEX_FILE=/tmp/…` inside the persistent shell. The export **outlived the probe**, so every later `git add`/`git commit` in this shell wrote into one scratch index instead of the repo's. Effect on the three repos:

```
.dotfiles   index=346  head=155  status=BROKEN
prescient   index=346  head=249  status=BROKEN
bro         index=346  head=346  status=OK
```

`git status` died with `fatal: unable to read <blob>`; `bro`'s index contained **dotfiles' `config/herdr/plugins/claude-name/names.py`** as a live entry.

Repaired: `unset GIT_INDEX_FILE`, deleted the scratch files, `git read-tree HEAD` in all three. Now 155 / 249 / 346 entries, all matching HEAD, `git status` clean in each.

**No work lost** — verified rather than assumed:
- dotfiles: all five audit docs tracked, `main...origin/main` in sync, HEAD is `e6934e9`
- prescient: 140 items in the store, **821 tests pass**
- bro: 16 commits intact, tree clean (only gitignored `data/`)

This is worth recording as a rule: **never `export GIT_INDEX_FILE`; pass it per-command** (`GIT_INDEX_FILE=… git add`). An exported index path silently redirects every subsequent git write in that shell, and it broke the working state of two unrelated repos before anyone noticed.

## The 16 commits — read and sound

Each message states the live observation that motivated it and the run/task id, which is what makes them reviewable later. The two most consequential:

**`3c483b0`** — the claim-without-effect invariant. `Held.holds = True` makes the agent's in-decision hub branch inert; `claims_have_effects` rebuilds an Effect from a `route` action at both `decide` and the commit (with `spec_hit`); consent to an offer becomes that offer's Effect. Reviewed earlier and mutation-tested: forcing the fallback back to `on` fails the assertions.

**`4a056ff`** — the duplicate-factory repro. The test drives four speculative prefixes with `holds` deleted and asserts exactly `4` creates, then with `holds = True` asserts **zero during decide** and **exactly one** `task_hub_effect` at the release. Its comment correctly notes that the old shape replayed against today's brain would give 1+N while the pre-fix code gave N. `bro/hubguard.py` trips on the three pre-fix runs and is clean on `155714`.

## ONE GAP in the newest commit — `99c165a`

The precedence flip (coordinator before Claude, per the owner's 16:07 correction) **ignores `available`**:

```python
if (c := next((d for d in dests if d.id == f"coordinator:{project}"), None)) is not None:
    return c
```

`Destination.available` is exactly whether that coordinator's pane is running (`bro_stack.py:97`, `available=via`). So when a project's coordinator is **down but its Claude is up**, `handler_for` returns the dead coordinator and never reaches the live Claude fallback — the opposite of the behaviour the docstring promises ("else its Claude, when no coordinator runs").

Verified directly:
```
handler_for('dotfiles', stack with coordinator available=False and claude available=True)
  -> coordinator:dotfiles | available: False
```

**Severity: not a data bug.** `PrescientStack.deliver` refuses honestly — it only hands to a coordinator when `dest.available`, otherwise returns `_not_running(dest)`. So the owner hears "the coordinator isn't running" instead of the card silently vanishing. That is the right failure, but it is a failure, and the fallback that would have worked is one line away.

**Fix:** select the coordinator only when available, else fall through to the Claude branch:
```python
if (c := next((d for d in dests if d.id == f"coordinator:{project}" and d.available), None)) is not None:
    return c
```
And add the case to `tests/test_coordinator_first.py`: coordinator present-but-down + Claude up → `agent:claude-…`. The existing tests only cover coordinator-up and coordinator-absent, which is why the gap passed.

## Verdict

Ship-ready apart from that one line. The corruption I caused is repaired and verified; the tests are behaviour-level, not plumbing; every commit cites the observation behind it.

**Unpushed, as agreed.** bro is 16 ahead of `origin/main`. Prescient and dotfiles are in sync.

---

## The which-slot spec — confirmed, and one addition

I verified the mechanism myself rather than accepting the description:

```python
# slot creation (voicebridge.py:2626 and 3 other sites)
self._which = (time.monotonic(), self.with_context(ptext, pid), msg_id, "fresh")
#                        ^when          ^text only — NO KIND     ^msg id  ^state
```

The consumer at `:2546` dispatches on **the presence of a project name**, not on what was asked:

```python
if which and ... and (project := self.named_project(text)):
    dest = self.handler_for(project, stack)
    return made(self.vary("pass", dest.label), [Effect(dest.id, dest.label, which[1], [which[2]])])
```

So the moment a project name arrives, a *status question* becomes a hand-over. `asks_status()` exists and is used elsewhere; it never gets a second look here. That is exactly the owner's 16:07 experience: "ask files what the status was" → "Which project?" → "Dot files" → routed as work.

**Addition to the spec I want on record:** the kind must be classified at **slot creation**, and the classifier must be able to say *"I don't know"*. If the slot records `kind` only when it is certain, an ambiguous request still becomes a task — which is the original bug wearing a label. The safe default for an unrecognised kind is to **answer and ask**, never to file. Also: the `which` slot must be cleared on **any** consumption path, including a status answer — otherwise a later "dot files" re-enters a stale slot. (The code deliberately does *not* clear on speculative prefixes, which is right; the clear belongs at commit.)

## The open question I am not deciding

Explicit "fix it" still going straight to the project's Claude is the owner's call, and the coordinator has put it to him. My read, for the record: it should go to the coordinator for the same reason `tk-a49ea85f1d54` did — the coordinator owns whether it or its Claude does the work — but it changes who receives explicit work, so it is his decision and the path stays untouched until he answers.

---

## Review of the which-slot build, in flight (2026-11-03 ~16:50)

The worker has the work uncommitted in `bro/voicebridge.py` (82+/7-). Read it while it is still cheap to change.

**Good, and better than the spec asked:** the consumption path dispatches on the stored kind exactly as specified —
`status` answers with no effect, `question` re-decides with the effects **stripped** (`q.effects = []`, route/propose
removed, unbacked reply replaced), `None` answers-and-asks and files nothing, and only `task`/`filing` reach
`handler_for`. `answered()` sets `clears_which` so the slot clears at the commit and never on a prefix. The
`handler_for` gap I found is fixed at `:3214` (`and d.available`).

**Finding 1 — `which_kind` is mislabelled on a whole family of requests.** `EXPLICIT` matches bare verbs, so
`explicit_filing` is true for:

```
'add a retry to the heinzel sync'                 -> 'filing'  (it is a task)
'tell heinzel to check the status of the sync'     -> 'filing'  (it is a task, arguably a status read)
```

Both matched on the single word `add` / `tell`. **Harmless for behaviour** — verified: `task` and `filing` take the same
branch, so both still hand on correctly. But it makes the telemetry lie, and the telemetry is the thing that is
supposed to make the next misfire diagnosable instead of inferred. Fix: test the stronger signals first —
`implied_task` / `TELL_TO` / `HAND_TO` / `SEND_IT` / `dev_request` **before** `explicit_filing`, since naming a
recipient or an action is more specific than the word "add". A two-line reorder, and the `which_slot {kind}` event
then means something.

**Finding 2 — `which_kind`'s docstring says "plainly one", but the classifier never returns `None` for a
request-shaped sentence.** `'the thing with the buffer'` correctly gives `None`, which is right. Just worth keeping the
`None` branch genuinely reachable: if every utterance ends up classified, the "answer-and-ask" safety net never fires
and we have the same silent assumption as before, only quieter.

Neither blocks. Both are cheap now and expensive after the commit.
