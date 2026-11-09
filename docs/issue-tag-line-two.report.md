# Report: the wrapper on its own line (docs/issue-tag-line-two.md)

Committed locally, not pushed. Files changed:
- `config/herdr/plugins/lifeview-fallback/lifeview.py`;
- `test_lifeview.py`;
- this report.

**To make it live:** restart the lifeview daemon.

## Reproduced, then fixed

```
prompt: '<pasted_content id="f3ce">\n[from:coordinator project:prescient id:omp-v35-wdp7] Real owner task'
HEAD:  owner   + event tag_unparsed {"where": "beyond the first line (treated as untagged)", ...}
new:   agent   untagged -> 'Real owner task'
```

## The rule now: strip harness wrappers, then anchor

```python
WRAPPER = re.compile(r"^\s*(?:<pasted_content\b[^>]*>\s*|auto:\s*)+", re.I)
TAG     = re.compile(r"^\s*\[from:(owner|coordinator|worker|harness|bro)\b([^\]]*)\]")
```

- `unwrapped()` removes any run of leading wrappers, whether on the same line or on their own lines. Then `TAG.match` must find the tag immediately after them.
- The first-line search and its 400-char cap are gone; anchoring makes both unnecessary.
- `untagged()` drops the wrappers, the tag, and a trailing `</pasted_content …>`. An untagged prompt is returned unchanged, wrapper included.
- **`tag_unparsed` stays.** Its `where` is now one of:
  - `at the start, malformed or unknown role`;
  - `after other text: a quoted tag, not honoured`.

## The four shapes

| Shape | Result |
|---|---|
| Same-line wrapper: `<pasted_content id="x"> [from:coordinator …] text` | **agent**, card text `text` |
| Wrapper on its own line (the reproduced prompt) | **agent**, card text `Real owner task`. With a coordinator or worker tag it opens **no card**, and no event fires. |
| `auto: [from:owner …] text` | **owner**, card text `text` |
| Tag after real prose: `here is a log:\n[from:harness …] x` | **Not honoured.** It gets today's untagged answer (`owner`), still cards as the owner's message, and logs `tag_unparsed` ("quoted tag, not honoured"). The same holds on the same line (`here is a log: [from:harness …] x`) and behind a wrapper (`<pasted_content>\nhere is a log:\n[from:coordinator …] x`). |

## Acceptance (`TagAfterWrapper`)

| # | Check | Result |
|---|---|---|
| 1 | Same-line wrapper → agent | PASS |
| 2 | Own-line wrapper → agent | PASS (also: no card for coordinator/worker, the closing wrapper stripped, no event) |
| 3 | `auto: [from:owner …]` → owner | PASS |
| 4 | Tag after real prose not honoured, logs `tag_unparsed` | PASS (three variants) |
| 5 | Several wrappers in a row | PASS: two paste wrappers, `auto:` plus a wrapper, upper case plus blank lines |
| 6 | Plain `[from:owner]` at the start | PASS |
| 7 | Untagged cases unchanged | PASS: the earlier set, plus "a wrapper alone is not a tag" |

Suites: `test_lifeview.py` **117 OK** (110 before); `test_peer.py` 17 OK, untouched.

## Earlier tests changed, deliberately

Four assertions from the previous round (`docs/issue-tag-not-at-start.md`) pinned "a tag anywhere in the first line counts". This issue reverses that: only harness wrappers may come before the tag, so a tag after prose is quoted, even on line 1.
- `"Round 25: see [from:owner] below"` is back to `agent`, and `"fix it [from:harness]"` back to `owner`. The test is renamed `test_only_a_tag_after_harness_wrappers_counts`.
- The 400-char-cap assertion is replaced by "a tag after prose on the same line is quoted".
- `untagged()` of a prose-then-tag prompt now leaves the prompt alone.
- The two expected `where` strings were renamed.

One side effect is gone: a first line that only *mentions* a tag ("what does [from:harness] mean?") no longer counts as tagged.

## Not done

- **No daemon restart.**
- **Shape rules are still anchored at the raw start.** An *untagged* wrapped message (`<pasted_content …>\nRound 25: …`) still defaults to `owner`. Stripping `WRAPPER` before the shape rules is a small follow-up, but it changes untagged behaviour (acceptance 7), so I left it.
