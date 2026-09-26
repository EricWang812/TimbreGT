# Demo script

Full version with timings and judge answers is in `docs/CONTEXT.md` §16.
This file is the runner's copy: what to click, in order.

Style rule: do not use em dashes.

## Before every run

Once per machine, only if missing (about 25 minutes in total, mostly Whisper;
the outputs are gitignored, so a fresh clone needs them again):

```
.venv/Scripts/python.exe -m scripts.warm_asr   # Whisper small, for make baseline and voice shopping
make eval       # needed by baseline and drift
make baseline   # fills #/baseline
make drift      # fills #/dashboard
```

Every run:

```
make reset
curl localhost:8100/healthz     # confirm the model is resident
```

After `make dev`, open the store once and click around before presenting: the
first load after startup can reload the page once (seen once in rehearsal, not
reproduced).

Then enroll the demo user live at `#/bank/enroll/maya`: 3 sounds x 5 takes,
recorded by the person who will approve in step 3. `make reset` wipes voice
enrollments and passkeys, so do this after every reset, and register the
passkey on the same page if you plan to show the fallback. If the bank says a
sound varied a lot, start it over with a different sound (a hum or a held
vowel is usually steadier): with fewer than 3 steady sounds, approval goes
straight to the passkey, by design.

## Sequence

1. Baseline page (`#/baseline`). Play two takes from one dysarthric speaker: the transcription check rejects both, Timbre accepts both. Point at the rates table: the transcription check also accepts other people who speak clearly.
2. Stay on the Baseline page. On the same example cards, point at the Timbre column: "Voice match score" against "Personal threshold", for the exact take the transcription check just rejected. Say the threshold comes from that speaker's own variability. (Speed is shown live in step 3.)
3. Shop page. Judge speaks an item; the store reads the suggestion back ("Say it again" repeats it). Confirm. Checkout; in the bank widget choose Maya's card and press "Read this payment aloud" (amount, store, card ending). The enrolled presenter says the two requested sounds. Point at the voice check panel: score, threshold, and "Checked in X seconds" (the under 2 seconds claim; it times the voice check itself, about 0.6 s in rehearsal, while the whole response also waits on Stripe, about 2.6 s). Receipt.
4. Devtools network tab. Merchant response shows two keys only.
5. Dashboard. Drift chart, adaptation on versus off.

## Insurance

Recorded video of the full flow lives at: (fill in path before Saturday)
