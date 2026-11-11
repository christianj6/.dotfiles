# Measurement: how many prescient tests touch the owner's real `data/`? (for docs/writepath-scope.md)

**Few. Only 2 of 73 pytest files touch the real `data/`, both through cwd-relative paths. So the redirect is cheap on the test side, and the read-only test server (fix b) does not have to come first.** The 8917 browser checks are the exception, and they are exactly what (b) is for.

This was measured, not fixed. The sweep was a read-only subagent's grep pass. Its key numbers are re-checked by hand and marked below. No tests were run and no server was started.

## Why so few

`tests/conftest.py` has **26 `autouse=True` fixtures** (checked). Every test runs under them, and they `monkeypatch.setattr(module, "CONST", tmp_path/…)` most data constants:
- mail, timeboxes, inbox, spaces, settings, tweaks, urgent, wraps, holidays, projects;
- finactuals, sketches, yearplan, usage, trello_cache, the autopilot/digest reports, meetings_done, events_hidden, placeorder, agent_board.

The task database goes through an env var instead, `PRESCIENT_TASKS_DB`.

So the suite already redirects data, one constant at a time and by name.

| class | test files |
|---|---|
| A: touches the real `data/` | **2** |
| B: also redirects constants itself | 20 |
| C: covered by conftest alone | 51 |
| **total** | **73** (checked) |

## A: the real-data tests

1. **`tests/test_sort_session.py`:** `sort_session.prep()` reads `PRIORITIES_PATH = Path("data/priorities.json")`, which `prescient/backlog/sort_session.py:27` defines relative to the current directory (checked). The test does not patch it. It reads only, and only if the file exists.
2. **`tests/test_week_priorities.py` (~:192):** `finalize()` writes `data/finalize-plan-<n>.json` relative to the current directory, then deletes it (`prescient/backlog/finalize.py:279`, checked). `apply_plan` is faked, but the file write is real. This is **a real write into the owner's `data/`** during the test run, small and self-cleaning.

**Outside pytest, run by hand against 8917:**
- `tests/finplan_pension_check.mjs` reads `data/finplan.json`;
- `tests/browser_token_check.mjs` reads `data/.server-token-8917`;
- `tests/browser_csp_check.mjs`.

All three drive the testserver, which serves and writes the real `data/`. That is the defect in the original finding.

**Uncertain:** `gcal.load_creds` reads a relative `data/` credentials file. Every test the subagent found that reaches it patches it out.

## What the cost actually is: the patches, not the data

The fixtures don't depend on the real data. They depend on **constant names**:
- **78 patch sites name a module constant** (checked: `cd tests && grep -hE "(setattr|patch(\.object)?)\(.*['\"][A-Z_]*(_PATH|_DIR|BACKUPS|DEFAULT_DB|CREDS_PATH)\b" *.py | wc -l`). 26 are in conftest, and 52 are spread across 18 test files: `sunsama_write.BACKUPS` 10, milestones 6, goals 5, eras 5, bucketlist 4, server 4 …
- **About 28 places read a constant directly**, e.g. `urgent.URGENT_PATH.write_text(…)`, across 11 files. This number comes from a rough grep and is not checked.
- **`inbox_write` copies a binding:** it does `from .parked_write import BACKUPS`, which conftest patches separately.

If the module constants become `data_dir()` calls, **all 78 patches stop redirecting anything, silently**. A test would then write wherever the resolver points. So the codemod and the test change have to land **together**: one autouse fixture sets `PRESCIENT_DATA_DIR=tmp_path`, which replaces the 78 patch sites, and the 28 direct reads are rewritten.

## Two scope corrections for docs/writepath-scope.md

- **Modules:** `grep -rn 'parents\[2\] / "data"' prescient/` finds **27** module files, not 30 (checked).
- **The seam has a second shape: cwd-relative paths.** These are `Path("data/…")`: autopilot `REPORT_PATH`, `PRIORITIES_PATH` in llm_sorter and sort_session, `sunsama_write.BACKUPS`, the gcal and sunsama_mcp `CREDS_PATH`, cli `tidy-plan`, and the finalize plan file. Both A tests are this kind. The proposed acceptance grep, `parents\[2\] / "data"` must be empty, **would pass with these still live**. It also needs `grep -rnE 'Path\("data/' prescient/`.

## What decides it

- **Fix (a) is cheap on real-data grounds.** Only 2 pytest files touch the real data, and both are one-line redirects once a resolver exists.
- **Its real cost is mechanical:** 78 patch sites and about 28 direct reads collapse into one conftest fixture, plus the module codemod. Both acceptance greps are needed.
- **The 8917 browser checks** are the live exposure, and nothing in pytest helps them. (b), or the testserver setting `PRESCIENT_DATA_DIR`, is what closes that.
