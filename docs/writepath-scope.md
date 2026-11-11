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
