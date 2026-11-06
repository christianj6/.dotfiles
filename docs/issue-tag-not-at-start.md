# Bug: a tag that is not at character zero is ignored (the echo's third cause)

Prescient's coordinator sent precise evidence: an echo card (`tk-695297b6575d`)
whose **own text contains the tag** —

```
auto: <pasted_content id="f3ce"> [from:coordinator project:prescient id:omp-v35-wdp7] The…
```

— was still created as `origin: owner`, `target: coordinator`.

## Reproduced

The parser is anchored:

```python
TAG = re.compile(r"^\s*\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]")
```

and the prompt arrives with the harness's own wrapper in front of our text:

```
<pasted_content id="f3ce"> [from:coordinator project:prescient id:omp-v35-wdp7] The message
  TAG.match -> False
  prompt_provenance -> "owner"          # the tag is right there, and is ignored
```

So a message *carrying* a correct tag produced an owner card. Several of the
day's echoes were this, not the coverage bug — which is why the sixth echo arrived
after the coverage fix.

## Why the wrapper exists

`<pasted_content id="…">` is the harness's framing for a pasted payload, and
`auto: ` is the card-title prefix. Either can precede the text, so **a tag is
never guaranteed to be at offset zero.** An anchor is the wrong rule.

## The fix

Read the tag as the **first `[from:…]` within the first line**, not at the start:

```python
TAG = re.compile(r"\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]")
# search, do not match, and only in the head of the prompt
def tag_of(prompt: str) -> tuple[str, str] | None:
    head = prompt.split("\n", 1)[0][:400]      # the first line only, bounded
    m = TAG.search(head)
    return (m.group(1), m.group(2)) if m else None
```

Guards, because a *search* is looser than an anchor:
- **first line only, capped** — a tag quoted deep in a pasted body must not
  retroactively re-attribute the message (someone pasting a log that contains a tag
  line should not have their message become that agent's);
- **the first match wins**;
- `untagged()` must strip the match wherever it was found, not just at the start, so
  the card's text does not carry the wrapper-and-tag prefix.

## And log the silent miss

Prescient asked for this and it is the right instinct: when a prompt **contains**
`"[from:"` but no tag parsed, emit a model event (`tag_unparsed`) with the first 120
chars. Then this class is visible next time instead of showing up as a mystery echo.
That is the same lesson as the `route_without_effect` and `covering` bugs: a silent
non-match is indistinguishable from "there was nothing to match".

## Acceptance

1. `<pasted_content id="x"> [from:coordinator project:p id:a] text` → **agent**, and
   for `[from:worker …]` → **no card**.
2. `auto: [from:owner …] text` → **owner**.
3. A plain `[from:owner]` at the start still works (no regression).
4. A message with a tag **only** in its second line or beyond is treated as untagged
   — quoting a tag must not re-attribute.
5. `untagged()` strips the tag wherever it is found, including after the wrapper.
6. A prompt containing `[from:` that does not parse emits `tag_unparsed`.
7. Existing untagged cases unchanged.

## Note on the echo

This plus the coverage fix plus the daemon restart should close it:
- **coverage**: a worker with an open item no longer opens another (`covering_items`)
- **comms**: `[from:coordinator]`/`[from:worker]` never card at all
- **parse**: the tag is now actually read when the harness wraps the text

The third is the one that was still letting messages through after the other two.
