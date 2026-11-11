# TASK: the plugin's writes are 403'd — it never sends the launch token

Heinzel's coordinator reported auto-tasks detected but never opened, plus a stream of echoed
text. **One cause, and it is mine.** Reproduced end to end.

## The bug

```
$ curl -X POST localhost:8765/api/tasks -d '{"op":"create", ...}'
{"error": "a write needs this launch's token (X-Prescient-Token; data/.server-token has it)"}
HTTP 403
```

`hub_open_task()` and every other plugin write call `http_json(HUB_URL + "/api/tasks", …)`
with **no token**. `grep X-Prescient-Token config/herdr/plugins/lifeview-fallback/lifeview.py`
→ nothing.

The requirement landed in the **write-path security work today** (`b0b84a6`, `27ffcef`), and
`_token_strict()` defaults to **on** (`os.environ.get(TOKEN_STRICT_ENV, "1") != "0"`). So
every auto-task create since that change has returned 403, `http_json` returned `None`,
`open_task` returned `None`, and `auto_task` logged nothing — **a silent failure behind a
diagnostic that said it had decided to open.**

That also explains the echo half: the owner's text arrives by *other* paths that still work,
so the only cards that appear are the ones produced elsewhere — which is exactly the pattern
heinzel described ("the echo path works and the work path does not").

## What to change (dotfiles plugin only)

1. **Read the token** the way the hub issues it: `data/.server-token` (default port) or
   `data/.server-token-<port>`. Take the port from `HUB_URL`. Read it lazily, per call — the
   file is written at launch and changes when the server restarts, so caching it at import
   would go stale exactly the way the daemon did.
2. **Send it** as `X-Prescient-Token` on every write to the hub. `http_json` already takes a
   body; give it an optional header (or a dedicated `hub_write()`), and route all writes
   through it so no future call site can forget.
3. **Never fail silently again.** When a write returns a non-200 or a `{"error": …}`, log it
   **once per shape** (the plugin already has `log()`/`report_once()`), so the next
   occurrence reads "auto-task create refused: 403 needs token" instead of nothing.
   `open_task` returning `None` must be visible.
4. **`--explain` must distinguish "will open" from "did open".** Today it prints
   `autotask_check(...)[1]` — the *why* string — which reads like a decision and is not one.
   Print the title too, and a line showing the last open attempt's outcome (ok / refused with
   the error). That single change would have made this bug self-diagnosing: the reporter
   reasonably concluded the detector had fired and nothing happened, and could not tell
   whether the open was even attempted.

## Acceptance — show, do not describe

1. `open_task` for a real agent returns an **id** (not `None`) and the item exists in the hub
   with the right `project`/`target`/`origin`. Paste the id and the `prescient task list`
   row.
2. A create with a deliberately wrong token returns an error **and** logs once; a create with
   no token file present logs a distinct, actionable line.
3. `--explain` prints, for an agent whose gate is open: the title it would open, then
   `open: ok <id>` or `open: refused <error>`. Verify on a live pane.
4. Existing plugin tests pass; add one for "a write without a token reports the refusal"
   and one for "a write with the token succeeds" (the hub can be faked).
5. No token is ever printed in a log line or an explain block.

## Why this happened, so it does not repeat

The write gate was added for good reasons (a probe wrote the owner's real settings file), and
the plugin was a write client that nobody listed. **Changing an API's requirements means
enumerating its callers** — the same "function checked, system inferred" failure as
`rule://fixed-claim-call-sites`. This time the API gained auth and one caller was missed; the
check is `grep -rn "http_json(HUB_URL" config/herdr/plugins/ | grep -v token`.

---

## End-to-end: what the fix proved, and one false pass to correct

The fix landed (`TOKEN_HEADER = "X-Prescient-Token"`, token read lazily, one write helper,
refusal logged, `--explain` now prints `open: <outcome>`).

**Verified by me, on the open path itself:**

```
open_task(omp-v36-w5p1d, "PROBE: token acceptance - safe to drop", turn)
  -> tk-5441ae6cc5ec
hub row: heinzel/coordinator, origin owner, note "opened by the lifeview harness"
```

That is the write path working where it previously returned `None` with a silent 403.

**A false pass to correct.** Heinzel's coordinator reported the end-to-end as passed and
cited `tk-5441ae6cc5ec` with `open: ok`. But that id is **my probe**, not their turn's card:

```
tk-5441ae6cc5ec  created 13:25:16  dropped 13:25:30  note "my token-acceptance probe"
no other heinzel card was created after 12:20
```

Their own pane's `--explain` right now says why:

```
auto-task: not work: a harness notification, a resumed session or a pasted image (never a card)
```

Their turn was **about the task system** — the correct refusal — so no card of theirs was
ever due. The `open: ok <id>` they read was the *last open attempt* recorded for that pane,
which happened to be mine.

Two lessons, both the same one this project keeps relearning:

1. **`open: ok` names an outcome, not a cause.** It is now the right line to read, but it
   records the last attempt for that pane — so a reader must check the id it names is *theirs*
   and recent, or the line proves someone else's write succeeded.
2. **A pass reported by a witness who cannot distinguish the evidence from a decoy is not a
   pass.** Their reasoning was sound and their report was honest; the id simply was not theirs.

**Still genuinely unproven: a real work turn on a non-dotfiles pane creating its own card.**
The open path is proven. The trigger-to-card loop under real work remains to be observed
end to end — the next ordinary 4-call turn on any pane, checked by comparing the hub's
newest id against `open: ok`'s id, is what closes it.
