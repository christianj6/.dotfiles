# Fourth cause: the harness wrapper is on its own line, so the tag lands on line 2

My "first line only" guard was correct in principle and wrong in scope. It is what
admits the echo now.

## Reproduced

```
prompt: '<pasted_content id="f3ce">\n[from:coordinator project:prescient id:omp-v35-wdp7] Real owner task'
  first line : '<pasted_content id="f3ce">'
  provenance : owner                     # the tag is on line 2, so the guard refuses to look
  event      : tag_unparsed {"where": "beyond the first line"}
```

`<pasted_content id="…">` is its own line, then our tagged text follows. The parser
searches only the first line, finds nothing, and falls back to `owner`.

All five post-fix echoes are this shape, all `project=prescient` — its pane receives
the wrapped form, which is why my own pane (whose prompts are already tag-first)
stayed clean and looked fixed.

## Why the guard existed, and what it should actually be

The guard was to stop a **quoted** tag re-attributing a message: someone pasting a log
that happens to contain `[from:coordinator …]` deep inside must not become that agent.
"First line only" was a crude approximation of "near the top".

The right rule is **only harness wrappers may precede the tag**, not arbitrary text:

```python
# strip leading harness wrappers, then look for a tag at what is now the start
WRAPPER = re.compile(r"^\s*(?:<pasted_content\b[^>]*>|auto:\s*)+", re.I)

def tag_of(prompt: str):
    rest = WRAPPER.sub("", prompt)
    m = re.match(r"\s*\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]", rest)
    if m:
        return m.group(1), m.group(2)
    # a tag anywhere else is a QUOTED tag: log it, never honour it
    if "[from:" in prompt:
        event("tag_unparsed", {"where": "not after a wrapper", ...})
    return None
```

So: **strip known wrappers, then anchor.** That honours the harness's own framing
(which is legitimate and ours) while still refusing a tag that a human or agent pasted
mid-text. It fixes this case without weakening the quoted-tag guard.

## Acceptance

1. `<pasted_content id="x"> [from:coordinator …] text` (same line) → **agent**.
2. `<pasted_content id="x">\n[from:coordinator …] text` (own line) → **agent**.
3. `auto: [from:owner …] text` → **owner**.
4. A tag **after real prose** — `"here is a log:\n[from:harness …]"` — is **not**
   honoured, and logs `tag_unparsed`.
5. Several wrappers in a row are handled.
6. Plain `[from:owner]` at the start still works.
7. Existing untagged cases unchanged.

## For the record: this bug had four causes

1. coverage agent-keyed → `covering` always empty (fixed)
2. daemon predating the parser (restarted)
3. tag not at character zero (search the first line — fixed)
4. **wrapper on its own line, so the tag is on line 2** (this one)

Each alone reproduced it. That is what "the echo" was: four independent ways for a
tagged message to be read as the owner's, wearing one symptom.
