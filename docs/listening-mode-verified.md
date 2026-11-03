# Listening mode: verified before it goes live (2026-11-03)

bro `52f5a08` (not pushed, 569 tests + go ok). Voice is down; the live core predates the tier. These are the checks I ran so the restart is a formality, not a gamble.

## The both-ways guard works

```
'I want you to enter a listening mode'  -> True
'just listen'                           -> True
'let me think out loud'                 -> True
'add a listening mode'                  -> False    (work on the feature)
'the listening mode is broken'          -> False    (a complaint about it)
'stop listening'                        -> False    (a mute phrase, not a request)
```

`listen_mode()` = `LISTEN_MODE` matches **and** `LISTEN_FEATURE` does not. The negative half is what matters: "add a listening mode" must stay dev work, or the owner asking for a feature change silently puts bro into a mode instead.

## Held thoughts survive a mute (checked, not assumed)

I expected a leak here — mute sets the tier from `Muted`-winning precedence, and I could not see where `heldThoughts` was cleared. It isn't cleared, and that is **correct**:

- `Held` (tier.go:418) has `Close`/`Hold`/`Len`/`Lapsed` — no discard path.
- `Classify` gives `Mute` precedence over `ListenClose` when tier ≠ Muted (tier.go:230), covered by `TestListeningClosesOnlyOnTheWholePhraseAndMuteWins`.
- Recovery is explicit at controller.go:1663: `s.tier == Active && heldThoughts.Len() > 0 && attention.Closes(...)` — after waking, a closing phrase still hands the whole stretch over as one turn.
- The lapse path says so too: "what was held is kept: a closing phrase still hands it over" (`listenLapsedLine`).

So no thought is lost by muting or by a quiet lapse. Good design; my suspicion was wrong.

**One real gap, minor:** the mute line is "Okay, I've stopped listening. Turn me back on from the tray." It does not say the thoughts are kept. Given `Held` is invisible state, an owner who mutes mid-thought has no way to know "I'm done" after unmuting will still hand it over. Suggest appending that when `heldThoughts.Len() > 0`. Cosmetic; not a blocker.

## The blocker on going live is prescient's UI, not bro

`LISTENING` renders as **"on"** in the life view (`listenRowsHtml` :4940, `broVoiceTag` :4994 map only STANDBY/MUTED). Spec routed: `docs/spec-prescient-listening-tier.md`.

Verified while writing it: **there is no UI action that closes listening.** `"stop listening"` is a mute phrase (tier.go:46); every close phrase (`ListenClose`, tier.go:223) is spoken. So prescient must show a disabled informational row, not invent an endpoint — the spec says this explicitly so nobody wires a 400.

Sequence therefore: UI lands → `make` → restart core. Not restart then patch.

## The owner's test row

`tk-fcf2134447ac` (bro/dev, origin owner, ready) — created 14:29:39, 31 s into the session. It is a **question** ("Do you have the listening mode thing, or is that not implemented yet") that became a work item; the dev agent answered it in the summary. bro has a fix in flight (`2026-11-03-question-about-feature-not-work.md`) with a replay acceptance of zero hub items.

**I am leaving the row alone.** It is the owner's store, it is already answered, and I have twice caused churn by "repairing" owner data on inference. Their call.

---

**The question that expects a listening mode (verified 2026-11-03, bro 981297a).** Asking "Do you have the listening
mode thing, or is that not implemented yet" must be **answered from bro's capability state, never proposed or
routed**. Live at 15:29 (run 20261103-152908) it was offered ("Want me to take a look at that?"), and "Yeah, sure I
just need an answer" was taken as consent, which created `tk-fcf2134447ac`. The replay acceptance, not a repair of
that row, is what holds it:
- `tests/test_question_about_feature.py` replays the run's utterances against a fake hub in prescient mode, on
  today's code and from the run's exact state (bro's offer, with its propose, already in the chat);
- both answer the question from the guide ("Yes. Say "just listen" …"), with **zero hub creates**;
- `agent._confirmed` refuses a yes that asks for an answer (`WANTS_ANSWER`);
- the change forms ("listening mode is broken", "make the listening mode better") still route as work.

---

**UI gate cleared (verified 2026-11-03, prescient c9a7948).** The claim that mattered was "the served page has it, so no
core-restart hazard remains". Checked the **served** bytes, not the file on disk:

- `curl localhost:8765/` → 5 hits for "holding your thoughts", the unknown-tier string present, `class="lw-tray-voice listening"` present
- CSS: `.lw-tray-voice.listening { fill: #7fb6d6; }` — light blue, never the grey that reads "off"
- `voiceWord()` is one shared resolver feeding both `broVoiceTag` and `listenRowsHtml`, so the tray and the menu
  cannot disagree — better than my spec, which asked for the same mapping in two places
- prescient's `/api/voice` is a transparent forward (`_forward_bro`), so `tier` reaches the page intact
- I mutation-tested the new assertions rather than accepting "verified": forcing the unknown fallback back to
  `'on'` fails **both** `broVoiceTag` and `listenRows`; restored → 821 passed

The unknown-tier rule holds in both directions — an unrecognised tier reads "unknown" in red-orange with
"bro reports a mode this page doesn't know", including for the unknown case, not just for LISTENING.

**Wording mismatch to watch in first use (not a blocker):** the tray tooltip promises "answers them all when you say
you're done", while the core's `kept()` line says 'say "your turn" and I'll answer them'. Both true, different
phrases named at different moments.

---

**Core restarted, listening mode live (verified 2026-11-03 15:43, bro core pid 45198).**

| Check | Evidence |
|---|---|
| started from the existing binary, no rebuild | pid 45198 `voice mic --live`; `bin/bro` made 15:36 with contract v11 + LISTENING present |
| startup event says the right store | run `20261103-154353` → `{"kind":"task_hub","source":"file","task_hub":"prescient"}` |
| `tier` survives prescient's forward | `GET localhost:8765/api/voice` → `{"running":true,"session":"live","tier":"ACTIVE","since_ms":42043,"state":"IDLE","output":"Beyond TV"}` — this is the exact object the page renders |
| hub untouched by the restart | 125 done / 2 ready before and after; **no row created after 14:43** |

The round-trip (`just listen` → `I am done`) has **not** been spoken yet — the core had just started. That is the one
thing still unproven by observation: `listen_done` handing the stretch over as one turn with zero effects. It is
covered by bro's own tests, but tests are not the owner's microphone, and the earlier hand-off taught that lesson
(the pipe worked while the *intent* was wrong).

**What to watch on the first real use:** the tray should read a light-blue "listening" — not grey (off) and not blank
(on). If it shows "on" while bro is silent, the page is stale and needs a reload; the served bytes are correct, so a
hard refresh is the fix, not a code change.
