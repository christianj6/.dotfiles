# Report: a tag not at character zero (docs/issue-tag-not-at-start.md)

Committed locally, not pushed. Files changed:
- `config/herdr/plugins/lifeview-fallback/lifeview.py`;
- `test_lifeview.py`;
- this report.

**To make it live:** restart the lifeview daemon. omp-peer is unchanged, so it needs no re-install for this.

## Reproduced, then fixed

The issue's exact prompt, classified by HEAD's code (before this commit) and by the new code:

```
prompt: <pasted_content id="f3ce"> [from:coordinator project:prescient id:omp-v35-wdp7] The message
HEAD: owner                 # the anchored TAG.match missed it -> an owner card (the echo)
new:  agent | untagged -> 'The message'
```

**The fix:** `tag_match()` searches, rather than matches, for the **first** `[from:<role> …]` in the prompt's **first line**, capped at 400 chars (`TAG_HEAD_CHARS`). `TAG` lost its `^\s*` anchor. All three readers go through it:
- `prompt_provenance`;
- the comms gate in `autotask_check`;
- `untagged()`.

**`untagged()`** removes the tag wherever it is found on the first line:
- **Framing before the tag** (a `<pasted_content …>` wrapper or an `auto:` prefix, `TAG_FRAMING`) is dropped with it, and so is the wrapper's closing `</pasted_content …>`. So the card says `auto: The message`, not `auto: <pasted_content id="f3ce"> [from:…] The message`.
- **Any other words before the tag stay:** `Round 25: see [from:owner …] below` becomes `Round 25: see below`.

## Both cases asked about

- **The pasted-content case:** `<pasted_content id="x"> [from:coordinator project:p id:a] text` gives **agent**. The same with `[from:worker …]` gives **no card**: "an agent-to-agent message ([from:worker]): comms, never a card". No `tag_unparsed` event, because it parsed.
- **A quoted tag in line 2:** `here is the log you asked for:\n[from:coordinator project:p id:a] Both landed` is **untagged**. It gets today's answer, `owner`, and still cards as the owner's request. Nothing is stripped from it. It does emit `tag_unparsed` with `where: "beyond the first line (treated as untagged)"`, so the miss is visible, as the issue asks: the prompt contains `[from:` and nothing parsed.

## `tag_unparsed`

Neither lifeview nor prescient has an event API to post to; I checked prescient's tree for one. So `event()` writes **one parseable line to the daemon log**:

```
[lifeview-fallback] 09:28:16 event tag_unparsed {"where": "beyond the first line (treated as untagged)", "head": "a log from earlier:\n[from:coordinator project:p id:a] quoted"}
```

- `head` is the first 120 chars.
- `where` is either `first line, malformed or unknown role` or `beyond the first line (treated as untagged)`.
- Emitted only when the prompt contains `[from:` and no tag parsed.
- **Once per prompt head:** the classifier runs on every 10 s tick, so without that it would repeat every tick. The memory is bounded at 512 heads.

If prescient wants the event in its own store, `event()` is the one place to point at an endpoint.

## Acceptance

| # | Check | Result | Test |
|---|---|---|---|
| 1 | `<pasted_content id="x"> [from:coordinator …] text` → agent; `[from:worker …]` → no card | PASS | `TagNotAtStart.test_1_*` |
| 2 | `auto: [from:owner …] text` → owner | PASS (also when the text looks like a round spec) | `test_2_*` |
| 3 | A plain tag at the start still works | PASS, all five roles | `test_3_*`; every earlier `MessageTags` / `TaskEcho` test passes unchanged |
| 4 | A tag only in line 2 or beyond is untagged | PASS: a quoted tag gets today's answer, still cards, is not stripped; a tag past the 400-char cap doesn't count either | `test_4_*` |
| 5 | `untagged()` strips the tag wherever found, including after the wrapper | PASS: the wrapper (and its close) or `auto:` go with the tag; other words before it stay | `test_5_*` |
| 6 | A prompt containing `[from:` that doesn't parse emits `tag_unparsed` | PASS: an unknown role, a missing `]`, a tag on line 2; one event across 5 repeats; silent when it parsed or there is no `[from:` | `test_6_*` |
| 7 | Existing untagged cases unchanged | PASS: no untagged test changed, all pass, and no event fires for them | `test_7_*` |

First match wins (`test_first_match_wins`).

Suites: `test_lifeview.py` **110 OK** (102 before); `test_peer.py` 17 OK, untouched.

## One test changed, deliberately

`MessageTags.test_only_a_leading_known_tag_counts` pinned the anchored rule this issue replaces:
- `"Round 25: see [from:owner] below"` was `agent` and is now `owner`;
- `"fix it [from:harness]"` was `owner` and is now `machinery`.

Both now follow the first-line rule. The test is renamed `test_only_a_first_line_known_tag_counts` and gains the line-2 case. Its other assertions are unchanged.

**What this means in practice:** a first line that *mentions* a tag counts as a tag. For example, "what does [from:harness] mean?" now classifies as machinery and opens no card. That is the cost of searching rather than anchoring. The first-line bound is what keeps a pasted body from doing the same.

## Not done

- **The shape rules are still anchored.** An *untagged* message behind a paste wrapper (`<pasted_content …> Round 25: …`) still misses its shape and defaults to `owner`. That is outside this issue, and changing it would alter untagged behaviour (acceptance 7). If wanted, a follow-up could strip `TAG_FRAMING` before the shape rules.
- **No daemon restart.**
- omp-peer's own "already tagged" check stays anchored. It sees the caller's raw text, which has no harness framing.
