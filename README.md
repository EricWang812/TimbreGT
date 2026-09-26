# Timbre

Payment approval that verifies who is speaking from the acoustics of a voice,
not from whether a machine can understand the words.

Built for HackGT 13 (Georgia Tech, September 25 to 27, 2026).

## Why

People with dysarthria (after a stroke, or with Parkinson's disease, cerebral
palsy, multiple sclerosis, or ALS) think and understand clearly, but their
articulation is impaired. Voice-gated systems in finance ask them to be
understood, so they are rejected, and the usual workaround is handing card
details to someone else. Identity lives in the acoustics of a voice;
intelligibility lives in articulation. Timbre checks the first and never the
second: nothing in the bank's verification path transcribes audio.

Dysarthric speaker verification is an existing research area (see
`docs/CONTEXT.md` §11 and `docs/RESEARCH.md`). Timbre is a deployment, not a
new algorithm: personal thresholds from a person's own variability, template
adaptation, a privacy split between store and bank, and a passkey fallback so
no one hits a dead end.

## What works

- A demo store and a separate bank service. The store learns only
  `{verified, transaction_id}`; tests enforce it.
- Enrollment of three personal sounds (a word, a hum, a vowel), five takes each,
  with held-out personal thresholds (ADR 3).
- Approval by two of those sounds in random order, replay rejection, template
  adaptation on confident passes (`docs/ALGORITHM.md` §7.4), and a real
  WebAuthn passkey only after two failed tries (a voice match approves any
  amount, ADR 12).
- Stripe test-mode payments behind a provider interface; the Visa Intelligent
  Commerce mapping is ADR 1 (no VIC access, stated plainly).
- Voice shopping on the store side (Whisper n-best, LLM rerank with a
  keyword fallback, yes/no confirmation) and spoken readback on both sides.
- Demo pages: `#/baseline` (a transcription check versus Timbre on the same
  corpus audio) and `#/dashboard` (adaptation over later sessions).

## What we measured (preliminary; small corpora)

| Claim | Number | Where | Caveats |
|---|---|---|---|
| Live design on an independent dysarthric corpus, repeated-sound protocol | EER 2.43% dysarthric, 0.29% control | ADR 9, `docs/PREREGISTRATION.md` | EasyCall, 30 speakers, Italian, 8 kHz upsampled, pre-registered |
| Same, against a same-word attacker | EER 2.84% dysarthric; FAR 0.63% at FRR 7.30% | ADR 9 | Exploratory, not pre-registered; corpus impostors, no synthetic voices |
| Text-independent check on TORGO | EER 8.8% dysarthric, 6.7% control | ADR 3, `make eval` | 11 evaluation speakers; different words per template |
| Transcription check vs Timbre on identical TORGO takes | Right person accepted 45% vs 64% (dysarthric); someone else accepted about 64% vs 0.8% | `#/baseline`, `make baseline` | Mixed per speaker; one speaker does worse with Timbre |
| Adaptation over later TORGO sessions | Own takes accepted 84% vs 66% static; impostors 2.0% vs 1.5% | `#/dashboard`, `make drift` | Sessions are days apart, not months |
| Cheaper tricks and other encoders | None adopted | ADR 7, 8, 9 | Each rejected by a rule set before looking |

## Run it

See `AGENTS.md` §4 (Windows notes in its Handoff section). In short: create the
venv, `npm --prefix web install`, `python -m scripts.warm_cache`, `make seed`,
`make dev`. Evaluation targets: `make eval`, `make baseline`, `make drift`,
`make variants`, `make models`, `make confirm`.

## For coding agents

Read `AGENTS.md` first (start with its Handoff section). `CLAUDE.md` only imports it. Companion docs in `docs/`.

## Credits and data

- TORGO dysarthric speech corpus: Rudzicz, Namasivayam, and Wolff, 2012.
- EasyCall corpus: Turrisi et al., Interspeech 2021, CC BY-NC 2.0, used for
  non-commercial evaluation only.
- Speaker model: SpeechBrain ECAPA-TDNN (VoxCeleb). Candidate encoders compared
  but not used live: WeSpeaker CAM++, ResNet34-LM (CC BY 4.0), ResNet221-LM, and
  SpeechBrain ResNet.
- Shopping speech recognition (store side only): Whisper small via faster-whisper.
- No corpus audio is redistributed in this repository.
- Product photos in `web/public/products/`: contributors to Open Food Facts,
  Open Beauty Facts, Open Pet Food Facts, and Open Products Facts, licensed
  CC BY-SA 3.0 (https://world.openfoodfacts.org and its sister projects).
  Prices in the demo catalog are approximate and set by hand.
