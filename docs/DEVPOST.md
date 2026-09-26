# Timbre: Devpost submission draft

Ready to paste. Numbers come from README.md, ADR 3, ADR 9, and
docs/PREREGISTRATION.md; keep each caveat with its number. No em dashes.

**Tagline:** Payment approval that checks who is speaking, not whether a
machine understood the words.

## Inspiration

Adults with dysarthria (after a stroke, or with Parkinson's disease, cerebral
palsy, multiple sclerosis, or ALS) think and understand clearly, but their
articulation is impaired. Voice-gated finance (phone menus, "say your card
number") asks them to be understood, so it rejects them, and the workaround is
handing card details to a family member. Identity lives in the acoustics of a
voice; intelligibility lives in articulation. Timbre checks the first and
never the second.

## What it does

Timbre is issuer infrastructure, like 3-D Secure, not an app. The store
integrates in two server-to-server calls.

- **Enrollment at the bank:** three sounds the person chooses (a word, a hum, a
  vowel), five takes each, recorded in alternating rounds. Each sound gets a
  personal threshold from the person's own held-out variability, never below a
  global floor.
- **Approval:** the bank's widget asks for two of those sounds in random order,
  compares them with a speaker embedding, and rejects replayed recordings.
  Nothing in the bank's verification path transcribes audio.
- **No dead ends:** after two failed tries, a real WebAuthn passkey completes
  the purchase. At $50 and above, the passkey is required as a step-up.
- **Privacy split:** the store receives only `{verified, transaction_id}`,
  enforced by a test.
- **Adaptation:** confident passes nudge the template, with a clamp on how far
  one update can move it.

Dysarthric speaker verification is an existing research area. Timbre is a
deployment, not a new algorithm: personal thresholds, adaptation, an
issuer-side privacy split, and a passkey fallback, wired into a payment flow.
As far as we could find, none of that had shipped.

## How we built it

A demo store and a bank, each a FastAPI service with its own SQLite file, and
a Vite plus React frontend. The speaker model is SpeechBrain ECAPA-TDNN.
Payments run through a `PaymentProvider` interface on Stripe test mode; the
bank stores a token reference and last four digits, never a card number.

**Generative AI, on the store side only.** Whisper small returns several
candidate transcripts of a shopping request. An LLM (Anthropic or Gemini,
temperature 0, strict JSON) reranks them against the catalog and returns a
product and a confidence; low confidence becomes a yes/no question, never an
open one. If the call fails or no key is set, a deterministic keyword match
takes over. The LLM path has not run live (no API key was configured), so we
claim no measured gain from it. Spoken confirmations deliberately use fixed
templates, not the LLM, split across the privacy boundary: a template cannot
misstate a number.

Evaluation uses corpus recordings only (TORGO, and EasyCall as an independent
check). No disabled speech was imitated.

## Challenges we ran into

- Scoring each enrollment take against a template that contained it
  overstated consistency most for the most variable speakers. We switched to
  held-out spread (ADR 3).
- Five takes recorded back to back captured one moment, not the person. We
  moved to interleaved enrollment (ADR 4).
- Four development speakers could not pick a better encoder (ADR 8), so we
  pre-registered one test on a second corpus.

## Accomplishments that we're proud of

- A privacy boundary that is machine-checked, not promised.
- Every failure path ends in something usable.
- We pre-registered a test, it failed, and we published the negative result:
  the encoder fusion we liked was rejected and ECAPA stays alone (ADR 9).
- Our own UI is keyboard-reachable, with visible focus, live regions, and 44 px
  targets.

## What we learned

Designing enrollment around a repeated personal sound paid off: on the same
EasyCall speakers, a text-independent check gave 8.75% dysarthric EER, the
product's repeated-sound protocol 2.43%. Silence trimming, a common cleanup
step, hurt dysarthric speakers (ADR 7).

## What's next

Sessions with real users, with consent (all our evidence is corpus audio).
UA-Speech as another independent check. A `VisaProvider` behind the same
interface. A cumulative drift cap. Measuring LLM reranking on versus off.
Defenses against synthetic voices.

## Visa Intelligent Commerce

We have no VIC access, so this is a mapping, not an integration (ADR 1).
Bank-side tokenization maps to **Tokenization**; the voice check is an issuer
step-up method under **Authentication**, with the passkey fallback VIC already
defines; the `instruction_id` bound to approval and authorization maps to
**Payment Instructions**; the outcome report maps to **Signals**. Gaps: our
tokens are Stripe payment methods, our passkeys are not Visa Payment Passkeys,
we found no published VIC hook for issuer-defined step-up, and on Stripe the
signal is only logged.

## Numbers and caveats

Preliminary, small corpora, correlated trials. Not a benchmark, not a
population claim, not a clinical result.

- **Live design, EasyCall (pre-registered):** EER 2.43% dysarthric, 0.29%
  control; at the calibrated margin (0.119; live is 0.12), FAR 0.23% and 0.02%, FRR 7.95% and 4.40%. One
  Italian corpus, 30 evaluation speakers, 8 kHz audio upsampled, corpus
  impostors (no trained imitators or synthetic voices).
- **Same-word attacker, EasyCall:** dysarthric EER 2.84%, FAR 0.63% at FRR
  7.30%. Exploratory, not pre-registered.
- **Text-independent, TORGO:** EER 8.8% dysarthric, 6.7% control. 11
  evaluation speakers; different words per template.
- **Held-out spread, TORGO (ADR 3):** false rejects fell from 72.9% to 36.3%
  (dysarthric) as false accepts rose from 0.00% to 0.83%.
- **Transcription check versus Timbre, identical TORGO takes:** right person
  accepted 45% versus 64% (dysarthric); someone else accepted about 64% versus
  0.8%. Mixed per speaker; one speaker does worse with Timbre.
- **Adaptation, later TORGO sessions:** own takes accepted 84% versus 66%
  static; impostors 2.0% versus 1.5%. Sessions are days apart, not months.

## Built with

Python, FastAPI, uvicorn, SpeechBrain (ECAPA-TDNN), PyTorch, torchaudio,
NumPy, SciPy, soundfile, faster-whisper (Whisper small), Anthropic or Gemini
API (optional reranking, not run live), Stripe (test mode), py_webauthn, SimpleWebAuthn,
SQLite, React, Vite, Web Audio API, Web Speech API (speech synthesis), Hugging
Face datasets and Hub, matplotlib, pytest, httpx. Data: TORGO (Rudzicz et al.,
2012), EasyCall (Turrisi et al., 2021, CC BY-NC 2.0, non-commercial evaluation
only), product photos from Open Food Facts (CC BY-SA 3.0).
