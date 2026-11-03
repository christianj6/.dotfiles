# Duplicate factory: diagnosed, and the restart fixed it (2026-11-03)

Four identical hub items from one utterance:

```
tk-b8fdc5c99e33  14:56:09  ready
tk-1c332dde48ea  14:56:10  queued
tk-5809a064b04e  14:56:10  queued
tk-2840f7a41414  14:56:12  queued
```
One distinct text, four rows. All `bro/dev`, origin `owner`.

## Mechanism — one speculation used four times

Run `20261103-154353` (the OLD core, pid 45198), utterance 35, "Yeah, throw that at your agent and let's uh see what happens":

```
rev=  3  used=True  utt=35  system=1  effects=0
rev=  6  used=True  utt=35  system=1  effects=0
rev=  7  used=True  utt=35  system=1  effects=0
rev= 14  used=True  utt=35  system=1  effects=0
```

Four separate speculative decisions for **one** utterance, each marked `used: true`, arriving 736.2 / 736.8 / 737.1 / 738.7 s — i.e. before that turn committed at 738.8 s. Each release produced an Effect with `dest = agent:omp-v34-wdp5`, and each Effect creates a hub item. Hence four.

It was not a single utterance: counted across the whole run, **10 utterances** had more than one `used: true` speculation:

```
utt 11: 2   utt 19: 9   utt 20: 2   utt 27: 2   utt 29: 3
utt 31: 3   utt 32: 3   utt 34: 5   utt 35: 4   utt 36: 2
```

So the duplicate factory had been running far longer than this one row set — the four I was shown were just the ones that reached the hub as creates.

## Verified fixed by the restart

Same measurement on the new core's run `20261103-155714` (pid 66531, made at 15:57):

```
utts with >1 USED speculation: []
```

**Zero.** So the duplicate factory was a property of the old core's build, and `make` + restart removed it. That is the useful conclusion — but I would mark it *observed on one short run*, not *fixed by design*: nobody has asserted what the old code did wrong, so a repro test does not exist. If it reappears, the telemetry signature to grep for is exactly the query above.

## What I am not doing

- **Not marking any of the four done.** Three are still `queued`; only the owner may drop a task (`store.done` refuses `dropped` from any other role), and I just finished fixing provenance so that an action is never recorded under a name that did not take it. Using `harness` to clear around the rule would be the exact thing `f9c305f` exists to prevent.
- Not creating a replacement for the idea. `tk-b8fdc5c99e33` is already `ready` and carries the idea; the owner's board entry points at it.

The three leftovers need one sentence from the owner, or a drop from the tray. They are duplicates of a row that is already `ready`.

## Correction to my own earlier report

I told both coordinators "task_hub_effect count for this run: 0" for run `20261103-154353`. **Wrong** — that run has 4. My filter checked top-level `kind` and then grepped a lowercased copy, so I missed them; the correct query reads every `effect`/`task_hub_effect` event with its timestamp. The claim that survived is the one that mattered (effects *inside* the LISTENING stretch 63.9–86.9 s = 0), but I got the number wrong and it is now corrected in `docs/listening-roundtrip-verified.md`.
