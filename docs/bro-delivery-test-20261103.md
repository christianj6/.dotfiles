# Bro pane delivery test — PASSED (2026-11-03 18:24)

Two deliveries into bro's own pane (`omp-v35-wdp5`, workspace `wD:t2`), on a clean
state (hub 159 done, nothing open, every agent idle).

## Test 1 — a delivery that must do nothing

Sent via prescient's own path (`agent.deliver_verdict`, the route the hub uses):

```
verdict: {'nudged': 'pending', 'detail': "typed into omp-v35-wdp5's REPL and
         the box looks submitted; no transcript shows it"}
```

`pending` was **conservative, not wrong**: the message had landed. Verified in
the transcript and by bro's pane going `working` within a second:

```
18:24:01  in_transcript=1  bro_omp=working
18:25:05  bro_omp=done
```

bro's reply, verbatim: **`ACK`**, then it stopped.

**No task was created.** Hub unchanged at 159 done, before and after.

## Test 2 — the same path, verdict unambiguous

```
verdict: {'nudged': 'ok', 'retryable': False, 'detail': "omp-v35-wdp5's transcript shows it"}
```

bro replied **`TWICE`**. Hub still unchanged.

## What this proves

1. **Delivery into bro's pane works** — both messages reached the transcript, and
   the `ok` verdict proves the transcript-confirmation path.
2. **The nested-REPL fix holds in this direction too.** Earlier I verified
   `ok` on `omp-v34-wdp7` and `omp-v34-wdp5`; these are the same survey after the
   v35 roll and the full provenance/auto-task work.
3. **Obeying "do no work" is respected.** Two explicit instructions not to create
   a task produced none — the harness did not manufacture one either, which is the
   provenance fix doing its job on a `pending`/quick turn.
4. **The `pending` verdict is honest, not broken.** It fires when the box looks
   submitted but the transcript hasn't caught up yet; the message then lands. The
   distinction between `ok` and `pending` is about *when the transcript is read*,
   not about whether the delivery worked.

## One residual worth naming

`pending` is indistinguishable, at the moment it returns, from a delivery that
genuinely failed. A caller that retries on `pending` would **double-deliver**.
The verdict already says `retryable: False`, which is the correct guard — but it
is worth remembering that `pending` means "watch the transcript", never "try
again".

## State after the test

Hub 159 done, nothing open. Every agent idle/done. No test artifact left behind:
neither the ACK nor the TWICE turn produced a hub item, a task, or a file.
