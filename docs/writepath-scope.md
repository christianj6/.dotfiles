# The write-path defect: measured scope, and why fix (a) as specced will not work

Prescient's coordinator found the right defect — a test server on port 8917 writes into the
owner's real `prescient/data/`, because the directory is derived from the package path, not
the port. It is the most valuable finding today. **But its fix (a) as written would miss
most of the writes.**

## Verified

```python
# prescient/gantt/server.py:168
DATA_DIR = Path(__file__).parents[2] / "data"
```

Port-independent by construction, so 8765 and 8917 share it. `testserver.py` has **zero**
`data/` redirection (grep: no matches).

## The part that changes the fix

`server.DATA_DIR` is **not** the seam. Modules do not import it — they each rebuild the
same expression at import time into their own module constant:

```
prescient/gantt/mail.py:41        SNOOZE_PATH  = Path(__file__).parents[2] / "data" / "mail-snooze.json"
prescient/gantt/mail.py:42        ORDER_PATH   = ... / "data" / "mail-order.json"
prescient/gantt/timeboxes.py:20   TIMEBOXES_PATH = ... / "data" / "timeboxes.json"
prescient/gantt/server.py:32      FINPLAN_PATH = ... / "data" / "finplan.json"
```

**30 modules** derive their own `data/` path this way. `server.py` has exactly **one**
`DATA_DIR /` use — the token path.

So "scope `PRESCIENT_TEST_SERVER` to its own data directory" cannot be done by redirecting
`server.DATA_DIR`: 29 modules would keep writing to the owner's real files, and the fix
would look complete while leaving the defect in place. **That is exactly the class of bug
this project keeps producing — a fix at the wrong seam.**

## What the fix actually needs

**One seam, then a redirect.** Pick one and make every module use it:

1. **A single resolver** — e.g. `prescient/data_dir.py` with `def data_dir() -> Path:` that
   reads `PRESCIENT_DATA_DIR` (default: the repo's `data/`), returning a **callable, not a
   module constant**, so an env change is honoured.
2. **Convert the 30 module constants to calls at use time.** This is the real work: a
   module-level `Path(...)` is frozen at import, before a test can set the env. Mechanical
   but wide — a codemod plus a grep that proves **zero** remaining
   `parents[2] / "data"` outside the resolver.
3. **Then** the test server sets `PRESCIENT_DATA_DIR` to a temp dir, and the guard is
   structural: an env var the process cannot ignore.

Cheaper interim if the 30-module change is too large right now: **fix (b), read-only test
server** — every write route returns a recorded fake. Narrower, keeps read realism, and it
*is* enforceable in one place (the write handlers), unlike (a). It also stops the bleeding
today.

## The grep that must exist afterwards

```
grep -rn 'parents\[2\] / "data"' prescient/ | grep -v data_dir.py     # must be empty
```

That single check is what stops the seam reappearing, and it is the same shape as
`check-coordinator-role.py` and the compaction-brief checker: a rule made checkable rather
than remembered.

## Order

1. Land the finding (this doc) — done.
2. **Measure the 30 modules' fixtures** before choosing: how many tests seed the owner's
   real `data/`? If few, the redirect is cheap; if many, (b) first.
3. Then (a) as one resolver + codemod, or (b) as the interim — with the grep as the
   acceptance either way.

## Also worth carrying

Three sightings of one defect today: the owner-default in the task dock, the invented actor
in a review, and now a test writing live owner data. The common shape is **a mutation
attributed to, or performed on, the wrong party** — a default that says "owner", a review
in someone's name, a probe writing real state. Fix (a) is the only one that removes the
possibility rather than the symptom.

---

## Measurement (worker, verified against the repo)

**2 of 73 test files touch the real `data/` — so the redirect is cheap and fix (b) does not
have to come first.**

Why so few: `tests/conftest.py` has **26 autouse fixtures** that monkeypatch data constants
to `tmp_path` by name (mail, timeboxes, inbox, settings, tweaks, goals, sketches, …), and
the task DB goes through `PRESCIENT_TASKS_DB`. The suite already redirects data — one
constant at a time.

| class | files |
|---|---|
| touches the real `data/` | **2** |
| redirects constants itself | 20 |
| covered by conftest | 51 |

The two real ones:
- `tests/test_sort_session.py` — reads `Path("data/priorities.json")`, read-only;
- `tests/test_week_priorities.py` — **writes** `data/finalize-plan-<n>.json` and deletes it:
  a genuine write into the owner's `data/` during a test run. Small and self-cleaning, but
  real, and it is the same defect as the 8917 case in miniature.

Outside pytest, the three `.mjs` browser checks drive the testserver against 8917 — those
**are** the original defect and (b) exists for them.

## The correction that matters: my acceptance grep was incomplete

I wrote:

```
grep -rn 'parents\[2\] / "data"' prescient/ | grep -v data_dir.py    # must be empty
```

**That misses a whole second family** — paths relative to the *current directory*:

```
prescient/backlog/autopilot.py:413      REPORT_PATH    = Path("data/autopilot-report.json")
prescient/backlog/llm_sorter.py:29      PRIORITIES_PATH = Path("data/priorities.json")
prescient/backlog/sort_session.py:27    PRIORITIES_PATH = Path("data/priorities.json")
prescient/gantt/sunsama_write.py:530    BACKUPS        = Path("data/backups")
```

(My own first grep returned 0 because I searched `prescient/gantt/` and `tests/` only —
another instance of searching where I expected the answer to be, which is the failure
`rule://fixed-claim-call-sites` names.)

So the acceptance check must be **both**:

```
grep -rn 'parents\[2\] / "data"' prescient/ | grep -v data_dir.py     # empty
grep -rnE 'Path\(["\x27]data/' prescient/ | grep -v data_dir.py        # empty
```

The cwd-relative ones are *worse* than the constant ones: they resolve against whatever
directory the process was started in, so a test run from `prescient/` and a run from
`~` write different files, and neither is the resolver.

## The real cost, restated

Not the fixtures — **78 constant-name patches** (the worker's count). The conftest already
knows the names, so the change is mechanical: each constant becomes a call to the resolver,
and the fixtures keep working because they patch the same names. That is the reason (a) is
affordable: it does not require redesigning the test suite, only converting references.

Uncertain and worth one check before landing: `gcal.load_creds` reads a relative `data/`
credentials file — every test found that reaches it patches it out, so it is likely fine,
but it is the one path nobody has driven end to end.
