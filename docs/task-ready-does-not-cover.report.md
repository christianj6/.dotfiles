# REPORT: a `ready` card covers the turn it went ready in

Spec: `docs/task-ready-does-not-cover.md`.

## Headline

- **The rule (one rule, by turn order, not by time or origin):** a `ready` item covers a
  turn only if that turn **started before the item went ready**, that is, if the item went
  ready during that turn. Everything else is as before:
  - the in-progress states still always cover;
  - a turn that starts after the ready event is new work and gets its card, however soon it
    follows and however old the card is.
- **Replayed against the real incident,** from the hub's own events for `tk-5edb44ae05ee`:

  ```
  13:56:35 working  (owner's "not quite")
  13:57:38 ready
  ```

  The duplicate `tk-84a4a895f73b` carries the session marker
  `[lifeview-session wD:p9@2026-11-19T14:56:3…]`, which is 13:56:3x UTC. So that turn
  started **before** 13:57:38, `tk-5edb44ae05ee` covers it under the new rule, and no second
  card is opened.
- **I did not use either of the rules the spec offered.**
  - **Recency (a time window):** I built and tested it first, and it broke the existing
    `test_4_owner_requests_still_card_and_complete_one_after_another`. The harness's own
    auto-ready puts card 1 in `ready` seconds before the owner's next message. A window
    swallows that follow-up request, which trades one bug for another.
  - **Owner origin:** every `auto:` card is `origin=owner` (all 43 auto twins in the last
    report were). "An owner-origin ready card covers regardless of age" would therefore make
    every long-ready card cover forever. That is exactly the "swallow every request he makes
    meanwhile" behaviour the `COVERING` comment says `ready` was removed to stop.
  - **So acceptance 3 is pinned the other way round:** origin does not change the rule. I
    flag this as a deliberate deviation from the spec. Turn order meets acceptance 1 and 2 and
    keeps test_4 green.

## Change (`config/herdr/plugins/lifeview-fallback/lifeview.py`)

- **`COVERING` is unchanged.** Its comment now documents the one extra rule for `ready`, with
  the incident and why neither a window nor origin works.
- **`ready_since(t)`:** the item's newest `ready` event. Open hub items carry their event log
  (`bro_tasks_via_hub`). Without one, as for bro's list, it falls back to `updated`.
- **`covers(t, turn_start)`:** returns
  - True for any state in `COVERING`;
  - `turn_start <= ready_since(t)` for `ready`;
  - False otherwise.

  With no turn known, `ready` does not cover.
- **`covering_items(agent, tasks, turn_start=None)`:** two callers.
  - The cheap pre-transcript check in `auto_task()` passes no turn. There `ready` does not
    cover, as before, so the transcript is read.
  - `autotask_check` passes `turn["start"]` and makes the exact decision.
- **Untouched:**
  - the `self.created` session marker and the history-note marker;
  - provenance, the comms tags and the trivial-turn threshold;
  - no title or text matching was added;
  - prescient's store.

## Tests (`test_lifeview.py`, 148 tests, all passing)

New tests in `TaskEcho`, named for the states they pin:

- **`test_ready_covers_the_rework_turn_it_went_ready_in`** (acceptance 1): the 13:57:38 replay.
  The turn started 13:56:35, ended 13:57:40, and is checked at 13:57:42; the result is
  `covered by tk-5edb44ae05ee (ready)`.
- **`test_long_ready_does_not_cover_new_work`** (acceptance 2): a card ready for 3 h does not
  cover a new request; a card is opened.
- **`test_just_ready_does_not_cover_a_request_that_started_after_it`:** a card that went ready
  15 s ago does not cover a request that started 10 s ago. This is the case a time window would
  get wrong.
- **`test_origin_does_not_change_the_ready_rule`** (acceptance 3, inverted as explained above):
  an owner-origin card ready for 3 h does not cover. A card that went ready during the turn
  covers for any origin: owner, agent or harness.
- **`test_ready_event_time_falls_back_to_updated`:** for an item with no event log.
- **`test_ready_never_covers_without_a_turn`:** the cheap pre-check.
- **`test_same_turn_guard_is_unchanged`** (acceptance 4): the session marker still stops a
  second card for one turn.

All existing tests stay green, including:

- `test_coverage_stays_inside_the_project_and_in_progress`, where a ready item with no turn
  does not cover;
- `test_never_duplicates`;
- `test_4_owner_requests_still_card_and_complete_one_after_another`.

**One test-harness fix:** `OwnerLifecycle.pane_turn`, which `TaskEcho` reuses, stamped
transcript entries from real time, while the fake hub's events use the test's clock, which
jumps 70 s per round. A second request then appeared to start 85 s *before* the first card
went ready, which cannot happen live. It now stamps on the test's clock. This is the only
change to an existing test helper, and no assertion changed.

## Live

- **The daemon is on the new code:** pid 54547, started 15:02:19, the lock holder. The
  `pgrep` count is 1.
- **A `workspace-up` bug I hit while deploying it (not fixed here, out of scope):**
  `workspace-up --only lifeview` reported `running (pid 54127) up 0s` and did not restart.
  54127 was a launch from herdr's event hook about to exit on the lock.
  - `workspace-up` judges freshness against the *newest* process matching
    `lifeview\.py --daemon`.
  - So whenever a hook launch is in flight, it compares the code against that launch and skips
    restarting the real, stale daemon (20359 here).
  - I restarted it by hand: `kill 20359`, then `python3 lifeview.py --daemon`.
  - The fix would be for `workspace-up` to judge the lock holder's pid (the lock file holds
    it). Flagged for the coordinator.
- **Acceptance 6:** no real "not quite" happened while I worked. To confirm on the owner's
  next one:

  ```
  prescient task list --project <project> --limit 5 --json    # no new auto: row created right after the reopened card's ready
  grep 'opened (auto)' ~/.local/state/herdr/plugins/dotfiles.lifeview-fallback/lifeview-fallback.log | tail -3
  python3 config/herdr/plugins/lifeview-fallback/lifeview.py --explain   # that agent: "covered by <id> (ready)" while its turn is in the window
  ```
