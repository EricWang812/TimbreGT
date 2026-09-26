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
grep -c "^OPENAI_API_KEY=." .env   # 1 means the agentic panel can reach OpenAI
```

Known-good code: tag `working-demo-2026-09-26` (full flow verified by a human
that day). If anything breaks after later changes, `git checkout
working-demo-2026-09-26` and restart `make dev`.

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
3. Shop page, "Shop a full request by voice or text" panel. Speak one whole request, for example "two cokes and as much yogurt as fits in ten dollars" (fills the cart: 2 Coke six-packs and 6 yogurts) or "what I need for tuna salad" (shows a list to check first, then Add to cart). If the mic or room noise misbehaves, type the same sentence in "Or type the whole request" and press Shop; it runs the same steps. Say that the cart is the confirmation: nothing is bought until checkout, and Undo takes it back out.
4. Check that the cart total is $50 or more (the tuna salad list plus two cokes comes to about $49 in items before tax and delivery; add one item from the aisles if the total is short). Checkout; in the bank widget choose Maya's card and press "Read this payment aloud" (amount, store, card ending). The enrolled presenter says the two requested sounds. Point out that voice alone approves it at any amount (ADR 12): no passkey after a match. Point at the voice check panel: score, threshold, and "Checked in X seconds" (the under 2 seconds claim; it times the voice check itself, about 0.6 s in rehearsal, while the whole response also waits on Stripe, about 2.6 s). Receipt.
5. Optional, if time: someone else tries the same card on a new checkout and is rejected, then the widget offers the passkey (never a dead end). Present it as one live illustration, not a result; the measured false-accept rates are in ADR 9. This is a different real person trying, which is fine; never have anyone imitate disordered speech (§2.3).
6. Devtools network tab. Merchant response shows two keys only.
7. Dashboard. Drift chart, adaptation on versus off.

## Insurance

Recorded video of the full flow lives at: (fill in path before Saturday).
Record it from a known-good run: agentic request, checkout over $50, owner
passes, second person rejected, receipt.

If OpenAI is unreachable after a recording, the agentic panel hands the same
audio to the older one-item Whisper panel above it, so the spoken request is
not lost. A typed request has no audio to hand over and shows an error; use the
older panel's typed field instead.
