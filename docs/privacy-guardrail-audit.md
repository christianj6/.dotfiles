# Privacy guardrail audit — tk-ad38d5755b32

The owner asked: "double check if this pre-commit hook is working properly… that we're properly preventing private information from leaking and that our automated tooling works properly."

**Verdict: the two guards work. There is one real hole at push time, and one stale claim in the docs.** Evidence below is from live tests, not from reading the code.

## What genuinely blocks (verified by running it)

| Test | Result |
|---|---|
| a credential assignment, staged | blocked, exit 1, names file:line and the pattern's label |
| an API-key shape | blocked |
| a home-anchored Desktop path | blocked |
| a "Source: <planning tool> task" line | blocked |
| "a normal line about the Desktop layout" | **clean** — no false block |
| Real `git commit` through `.githooks` in a scratch clone | **commit exit 1, HEAD unmoved** — the commit did not land |
| `check-private.py --all` on the current tree | clean |

The allowlist works too: `private-patterns.txt` quoting its own regexes and the placeholder `.claude/sessions/<pid>` forms are correctly not flagged. That matters — a guard that cries wolf gets disabled.

The extension's command matcher is solid. All of these match:
```
git commit -m x                         MATCH
git -c user.name=x commit -m y          MATCH
git commit --no-verify -m z             MATCH   <- the bypass it exists for
cd /tmp && git commit -m a              MATCH
echo hi && git commit -am w             MATCH
git push                                MATCH
```

## THE HOLE: push-time scanning looks at the wrong content

The extension treats `git commit` **and** `git push` identically — it always runs `check-private.py --staged`. For a push, staged content is usually empty, and the content actually being published is already **committed**.

Reproduced in a scratch clone:

```
$ echo "<a credential assignment>" > sneaky.md
$ git commit --no-verify -m bypass          # hook bypassed → lands
$ git diff --cached --name-only | wc -l
0                                            # nothing staged
```

So: `--no-verify` + `git push` publishes private content while the extension reports clean, because it audits an empty index. The extension's own header says it "cannot be bypassed" — that is true against `--no-verify` *via a tool-call commit*, and false via a shell that commits with hooks off and then pushes.

There is also **no `pre-push` hook** (`.githooks/` contains `pre-commit` only).

### Fix, smallest first

1. **`.githooks/pre-push`** that runs `check-private.py --all` — covers every push from this clone regardless of how the commit was made. This is the one that closes it, and it is a three-line hook.
2. In the extension, branch on the verb: `push` → run `--all` (or better, scan the range about to be pushed); `commit` → `--staged` as today.
3. A push that has nothing to push costs nothing, so `--all` on push is cheap insurance.

## Stale claim in the guard's own header

`config/omp/extensions/omp-privacy-guard.ts:5` still advertises:

```
//   CI (check-private.yml) -> full tracked-tree audit on push + daily
```

There is **no `.github/` directory at all**. Commit `7c97431` ("drop CI layer from privacy guardrail") removed it deliberately. `AGENTS.md` is corrected (it lists two layers), but the extension header was not, so an agent reading the code is told a third layer exists that does not. Either restore CI or delete those two lines — but the docs must not claim a guard that is not there.

Related: the scanner silently skips files over `MAX_FILE_BYTES` (2 MB) and unreadable ones. No tracked file currently exceeds it (checked), so no blind spot today — but a future vendored blob would be skipped *silently*. Worth a one-line warning when it skips rather than nothing.

## Also checked, fine

- `core.hooksPath = .githooks` is set, so plain `git commit` in this clone runs the hook.
- The scanner's exit codes are honoured by the hook (`exec` propagates).
- Patterns cover credentials, home-anchored paths, and transcript content — matching the owner's 2026-10-05 scope decision (project names and one-line board bookkeeping are intentionally publishable).

## The guard blocked this very document (good sign)

The first commit of this audit was **rejected by the hook** — it quoted the literal test strings it was reporting on (a credential assignment, a Desktop path, a planning-source line). That is the guard doing exactly its job on real content, in the same minute. The examples above are therefore described rather than reproduced; the patterns are in `scripts/private-patterns.txt` if the exact forms are needed.

Worth knowing: **this is a real friction for maintenance.** Any future doc *about* the guardrail will be blocked unless it paraphrases. Two options: paraphrase (what I did), or add a narrow allowlist for `docs/privacy-guardrail-audit.md` — which I do **not** recommend, since an allowlisted file is exactly where a real leak would later hide.

## Recommendation

Item 1 (pre-push hook) is a genuine security gap and cheap to close; item 2 is the same fix done properly. Item 3 is a documentation lie that will mislead the next agent. None of them is urgent enough to interrupt bro's voice work, and none requires touching `private-patterns.txt`.
