# Watching heinzel's playtest round (2026-11-03 16:40–17:00)

The owner handed heinzel new playtest feedback and asked me to watch whether it
works and returns for a check.

## What I found — two things, one real

**1. It is working, not stuck.** Claude (`claude-v2-w5p1a`) has been continuously
active for ~15 minutes:
- `prototypes/slice/tests/test_slice.cpp` modified in the working tree;
- last commit `ef9037e9` "round 25's board moves and the one-look panel";
- its live transcript was written seconds before I read it, on a z-fighting edge
  in the pale panel — i.e. genuine iteration on a rendering bug.
- the heinzel **omp pane is idle**, which is correct: the work is its Claude's,
  and the omp's job here is coordination, not the code.

**2. No hub item exists for this round, so the green icon cannot fire.** The hub
has zero open heinzel items (`open=0` throughout). The feedback went to the
Claude as a chat prompt, not through a hub task. auto-ready only ever acts on
**hub items**, so:

- the icon will stay **amber while working**, and
- when Claude settles it will go **grey**, because nothing tracked is open.

That is the *same shape* as the original complaint, but a **different cause**:
not a broken predicate, but an absence of tracked work. The predicate is fine —
verified — it simply has nothing to mark. A round that is not carded cannot turn
green.

## What "comes back to me for a check" will look like

Not a hub item. Either:
- a Trello card moved to **Check** (the owner's review gate), or
- the Claude plainly asking in its pane.

If the owner wants heinzel rounds to be *tracked* — carded, and therefore able to
go green — that is a decision about how heinzel work is filed, not a bug fix.

## One thing I fixed while watching

`--explain` showed heinzel's **idle** omp as `icon: working`, because the
project's Claude was busy. `resolver_status` is per **project**; the explain loop
draws one icon per **agent**, so the project's answer painted every row — and the
`why` line attributed it to herdr, which had said idle. Now only the row the
resolver names may claim its answer, labelled `(from prescient, for <agent>)`.

Diagnostic-only (the real icon path never calls `resolver_status`), but the
diagnostic is what you read when you distrust the icon, so it must not lie.
4 tests pin it, including "a busy project must not paint an idle agent".
