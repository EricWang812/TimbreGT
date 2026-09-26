# Demo script

Full version with timings and judge answers is in `docs/CONTEXT.md` §16.
This file is the runner's copy: what to click, in order.

Style rule: do not use em dashes.

## Before every run

```
make reset
# once per machine, not per run: make eval && make baseline (about 15 minutes, needs scripts.warm_asr)
curl localhost:8100/healthz     # confirm the model is resident
```

## Sequence

1. Baseline page (`#/baseline`). Play two takes from one dysarthric speaker: the transcription check rejects both, Timbre accepts both. Point at the rates table: the transcription check also accepts other people who speak clearly.
2. Approval page. Same clip. Show score and personal threshold. Under 2 seconds.
3. Shop page. Judge speaks an order. Confirmation read back. Approve. Receipt.
4. Devtools network tab. Merchant response shows two keys only.
5. Dashboard. Drift chart, adaptation on versus off.

## Insurance

Recorded video of the full flow lives at: (fill in path before Saturday)
