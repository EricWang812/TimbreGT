# Algorithm, data, payments, and AI usage

Part of the Timbre instruction set. Read `CLAUDE.md` first.
**Read this file before touching `issuer/verification.py`, `ml/`,
`issuer/payments/`, or `api/llm.py`.**

Style rule: do not use em dashes in anything you write in this repo.

---

## 7. The core algorithm (do not redesign without logging why)

Implementation lives in `issuer/verification.py`. **Every numeric constant below
lives in `issuer/config.py` as a named constant.** No inline literals, ever,
because we will be retuning these live during the event.

### 7.1 Embedding

Input: 16 kHz mono float32. Output: L2-normalized 192-dimensional ECAPA vector.

Peak-normalize the waveform before encoding. **Assert the sample rate is exactly
16000 and raise if it is not.** Do not silently resample server-side: a mismatch
between enrollment and verification sample rates produces low scores that look
exactly like an identity mismatch, and you will spend hours debugging the model
instead of the audio.

Because vectors are unit length, cosine similarity is a plain dot product.

### 7.2 Enrollment

For each of the 3 sound labels, capture 5 recordings (15 total).

Per label:
1. Reject any recording shorter than `MIN_DURATION = 1.2` seconds or with RMS
   below `MIN_RMS = 0.01`, with a specific message the UI can act on
   ("too short, hold the sound a little longer").
2. Compute `cohesion` = mean pairwise cosine across the 5 embeddings, excluding
   the diagonal.
3. If `cohesion < COHESION_MIN` (0.55), do **not** hard-fail the user. That
   would violate non-negotiable §2.4. Instead:
   - Offer to re-record that label once with clearer guidance.
   - If it fails again, accept the enrollment, mark the label
     `low_confidence = true`, exclude it from challenge selection, and require
     the passkey fallback for that user until another label is enrolled.
   - Log the event. A user who cannot enroll is a finding worth reporting
     honestly, not an error to hide.
4. Store the L2-normalized centroid, plus `spread` = mean cosine of each
   sample to the centroid of the *other* four (held out; see
   `docs/DECISIONS.md` ADR 3). The in-sample version, which includes each
   sample in its own centroid, overstates consistency, and overstates it most
   for the people whose takes vary most.

### 7.3 Personal thresholds (this is the design contribution)

```python
threshold = max(GLOBAL_FLOOR, tpl.spread - THRESHOLD_MARGIN)
# GLOBAL_FLOOR = 0.45, THRESHOLD_MARGIN = 0.12
```

A speaker whose own recordings vary more gets a looser personal threshold, but
never below the global security floor. A single global threshold penalizes
people for exactly the characteristic that defines their condition.

State this out loud during judging. It is the difference between "we ran a
pretrained model" and "we designed for this population."

### 7.4 Adaptation (the part no shipped product does)

Run only on a confident pass, meaning `score >= threshold + CONFIDENT_MARGIN`
(0.10). A borderline pass must not update the template.

```python
new = (1 - ALPHA) * centroid + ALPHA * v          # ALPHA = 0.12
new = new / norm(new)
# clamp: if dot(new, old) < 1 - MAX_DRIFT, pull new back toward old
#        until the constraint holds.   MAX_DRIFT = 0.05
```

Write every resulting drift value to the `verifications` table. Rationale: an
ALS user's voice changes month to month, and a static voiceprint enrolled in
January rejects them in June. The clamp prevents an attacker from walking the
template toward their own voice over repeated attempts.

### 7.5 Liveness and anti-replay

All three are required. A judge will ask about replay.

1. **Randomized challenge.** The server picks 2 of the user's 3 sound labels at
   random and requires them in the order given. A single stolen recording cannot
   satisfy the sequence. Labels marked `low_confidence` are excluded.
2. **Near-duplicate rejection.** Normalized cross-correlation above
   `REPLAY_CORR = 0.98` against any stored sample means the same file was
   replayed. Reject and count it as a failed attempt.
3. **Amount tiering.** Below `STEP_UP_AMOUNT` (5000 cents), voice alone. At or
   above it, voice **and** passkey.

### 7.6 Fallback

After `MAX_VOICE_ATTEMPTS = 2` failures in one approval, the issuer returns a
challenge requiring WebAuthn. The passkey path must complete a real purchase.
The merchant response is identical in shape either way, so the merchant cannot
tell which path was used (non-negotiable §2.5).

---

## 8. Data

**Primary:** `abnerh/TORGO-database` on HuggingFace. About 16,552 rows, short
words and restricted sentences only, filenames of the form
`FC01_1_arrayMic_0066.wav`.

**Backup:** `pranaykoppula/torgo-audio` on Kaggle, organized as `con/` and
`dys/` top-level folders with speaker subfolders.

Speaker ID prefixes: `F` and `M` are dysarthric speakers, `FC` and `MC` are
controls.

```python
import re, os

SPEAKER_RE = re.compile(r"^([FM]C?\d+)")

def speaker_of(path: str) -> str:
    m = SPEAKER_RE.match(os.path.basename(path))
    if not m:
        raise ValueError(f"cannot parse speaker from {path}")
    return m.group(1)

def is_control(speaker: str) -> bool:
    return speaker[1] == "C"        # FC01, MC04 -> control; F01, M05 -> dysarthric
```

If the HuggingFace dataset exposes a `speech_status` field, prefer it over
filename parsing and use the parser only for speaker identity.

### 8.1 Data rules

- **Filter to one microphone type.** TORGO contains `arrayMic` and `headMic`
  recordings. Mixing them means you are measuring microphones rather than
  people. Default to `headMic`. Record the choice in `docs/eval_results.md`.
- **Split development and evaluation by speaker, never by clip.** Within an
  evaluation identity, enrollment and genuine probes must share identity but
  never share recordings. Prefer different sessions and disclose fallbacks.
  Do not tune thresholds on evaluation identities (ADR 6).
- **Speaker count is small.** TORGO has roughly 15 speakers total. Count the
  exact number after loading and print it. Report results as preliminary, on a
  small corpus, with N stated on every chart. Do not call it a benchmark.
- **`data/` is gitignored. Never commit audio.**
- Cite Rudzicz et al. 2012 for TORGO in the README. Cite Kim et al. for UASpeech
  only if we actually use UASpeech.

---

## 9. Payments

### 9.1 Reality check

Visa Intelligent Commerce is a gated product requiring an access request. Visa
support states there is no set timeline for review, and community reports range
from 10 business days to no response at all. **Assume it will not be approved
before or during the event.** Do not build anything on the assumption it will
arrive.

### 9.2 Therefore

- Build against the `PaymentProvider` ABC. Select the concrete provider with the
  `PAYMENT_PROVIDER` environment variable. Never import a concrete provider
  outside `issuer/payments/`.
- Ship on Stripe test mode.
- Separately, get one real authenticated Visa sandbox call working (Visa Direct
  sandbox is open to any developer) purely to prove we cleared two-way SSL.
  Capture the response and put it in the Devpost.
- Write `docs/DECISIONS.md` mapping each step of our flow onto Visa Intelligent
  Commerce capabilities: payment token provisioning and lifecycle, cardholder
  step-up verification, passkey management, and commerce signals. Platform
  fluency is what is being scored, not whether we cleared their partner review
  in 36 hours.

### 9.3 Interface

```python
@dataclass(frozen=True)
class TokenRef:      # opaque handle to a stored payment credential
    value: str
    last_four: str
    nickname: str    # "blue Chase card"

@dataclass(frozen=True)
class AuthResult:
    ok: bool
    auth_id: str | None
    decline_reason: str | None

@dataclass(frozen=True)
class CaptureResult:
    ok: bool
    transaction_id: str | None

class PaymentProvider(ABC):
    def create_token(self, user_id: str, test_card: str) -> TokenRef: ...
    def authorize(self, token: TokenRef, amount_cents: int,
                  merchant_id: str, instruction_id: str) -> AuthResult: ...
    def capture(self, auth_id: str) -> CaptureResult: ...
    def report_outcome(self, instruction_id: str, outcome: dict) -> None: ...
```

`instruction_id` is generated by the merchant when the user confirms a cart, and
binds the verification result to the authorization. Keep it even on Stripe,
where it is otherwise unused: it mirrors Intelligent Commerce's instruction
controls and makes the mapping document honest rather than aspirational.

`test_card` accepts a sandbox test card number, is used once to create a token,
and is never persisted (non-negotiable §2.2).

---

## 10. Generative AI usage (required by the challenge)

The Visa brief demands generative AI. A bolted-on chatbot reads as bolted-on.
Use it only where it is load-bearing for this specific user.

1. **N-best reranking (headline use).** ASR on dysarthric speech is unreliable,
   but the correct answer is often somewhere in the top-k hypotheses rather than
   the first. Pass the n-best list plus the catalog; the model returns a product
   ID and a confidence score. **Measure intent accuracy with reranking on versus
   off.** That delta is a second demo number.
2. **Yes/no repair loops.** When confidence is below `INTENT_CONFIDENCE_MIN`
   (0.7), ask a question answerable with one syllable, a nod, or a tap. Never
   ask an open question of someone who is hard to understand: re-explaining is
   the failure they are already experiencing.
3. **Spoken confirmation.** Compose item, total including shipping and tax, card
   nickname, last four, and merchant. Pass all numbers in as data and forbid
   arithmetic in the prompt so the model cannot produce a wrong total.
   *As built (2026-09-26):* split along the privacy boundary and filled from a
   fixed template, not the LLM. The store reads back the item and price after a
   spoken request (`web/src/lib/speak.js`); the bank widget reads back amount,
   merchant, card nickname, and last four on request (`web/src/issuer/speak.js`).
   Neither side holds all five fields (the issuer never sees items, ADR 2), and
   a template cannot misstate a number. Browser speech synthesis; no network.
4. **Dispute drafting.** Covers the post-purchase stage of the brief and removes
   the phone-tree barrier the whole project is about.

Every LLM call: strict JSON output, `temperature=0`, parsing wrapped in
try/except, and a deterministic fallback (keyword match against the catalog) if
the call fails or the response does not parse. The demo must not depend on a
network round trip succeeding.

---
