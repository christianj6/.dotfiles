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
