# Architecture decision records

Add an entry here whenever a change alters a §7 parameter, an architectural
boundary in §5.1, or a non-negotiable in §2. Record the alternatives considered
and why they were rejected.

Style rule: do not use em dashes.

---

## ADR template

```
## <number>. <decision>
- **Date:**
- **Status:** proposed | accepted | superseded by <n>
- **Context:** what forced a decision
- **Decision:** what we chose
- **Alternatives rejected:** and why
- **Consequences:** what this makes easy, what it makes hard
```

---

## 1. Visa Intelligent Commerce mapping (write this during the event)

Required for the Devpost submission. For each step of our flow, name the VIC
capability it corresponds to:

| Timbre step | VIC capability |
|---|---|
| Card enrollment in setup | payment token provisioning and lifecycle |
| Acoustic verification at approval | precedes cardholder step-up verification |
| Passkey fallback | passkey management |
| instruction_id binding | user instruction controls |
| Receipt and outcome reporting | commerce signals |

Status: not yet written. Owner: integration and pitch role.

---

## 2. Issuer-hosted challenge; the merchant sends no identity

- **Date:** 2026-09-25
- **Status:** accepted
- **Context:** The original CLAUDE.md §1.1 snippet had the merchant POST the
  shopper's `audio` to `/v1/approve`. That contradicts §5.1, which says the
  merchant must never learn which sound label was challenged or how many
  attempts occurred: to relay audio, the merchant would have to relay the
  challenge prompts and every retry, and it would hold biometric audio.
- **Decision:** The issuer hosts the challenge, as a 3-D Secure access control
  server does. The merchant makes two server-to-server calls:
  `POST /v1/sessions {instruction_id, amount_cents, merchant_id}` returns an
  opaque `session_id`, and `POST /v1/approve {instruction_id}` returns
  `{verified, transaction_id}`. The browser hands `session_id` to the issuer
  widget (`web/src/issuer/`, which imports only `issuerApi.js`), and audio and
  passkey assertions go from the widget straight to the issuer. The merchant
  sends no cardholder identity either: the cardholder is identified inside the
  widget, and the issuer rejects any extra field on `/v1/sessions` with 422.
- **Alternatives rejected:** (a) Merchant relays audio, per the old snippet:
  leaks challenge labels and attempt counts, and puts biometric audio in
  merchant hands. (b) Merchant sends `user_id` so the issuer knows whose card
  to charge: gives the merchant a cross-merchant identifier and is not how
  card payments identify a cardholder.
- **Consequences:** Devtools shows audio going only to `:8100`, which makes
  the privacy demo stronger. The merchant integration is still two calls and
  a hand-off. The issuer now serves a small browser-facing surface (the
  widget endpoints), so it needs CORS for the web origin. `orders` has no
  `user_id`, and `sessions.user_id` is NULL until the widget binds it.
  Enforced by `tests/test_boundary.py`.

---

## 3. Personal threshold uses held-out spread

- **Date:** 2026-09-25
- **Status:** accepted (to be confirmed by the Phase 8 evaluation)
- **Context:** §7.3 sets `threshold = max(GLOBAL_FLOOR, spread - THRESHOLD_MARGIN)`,
  with `spread` originally the mean cosine of the 5 enrollment samples to
  their own centroid. Every sample is part of that centroid, so the number is
  optimistic. On the first real enrollment (one typical speaker, 3 sounds,
  15 takes) the in-sample spread overstated a fresh take's score by about
  0.10, and only 11 of 15 held-out takes cleared their threshold. With a
  2-of-3 challenge that needs both takes to pass, that is roughly a coin flip
  per attempt. The overstatement grows with variability, so it penalizes
  most exactly the speakers the personal threshold exists to help.
- **Decision:** `spread` is the held-out (leave-one-out) mean: each sample
  scored against the centroid of the other four. `GLOBAL_FLOOR` and
  `THRESHOLD_MARGIN` are unchanged. On the same data, thresholds moved from
  0.70 to 0.72 down to 0.60 to 0.62, and 14 of 15 held-out takes pass.
  `in_sample_spread()` is kept only for the evaluation.
- **Alternatives rejected:** (a) Keep the in-sample formula: more genuine
  approvals fall to the passkey, and the bias varies per speaker, so later
  tuning would be done on distorted numbers. (b) Lower `THRESHOLD_MARGIN`
  instead: shifts everyone equally and leaves the per-speaker bias in place.
- **Consequences:** Lower thresholds mean fewer false rejects and possibly
  more false accepts. Evidence so far is one speaker and 15 takes of typical
  speech, which is a direction, not a benchmark. Phase 8 must report false
  accepts and false rejects on TORGO for both formulas side by side; if false
  accepts are too high, decrease `THRESHOLD_MARGIN` (which raises the threshold) and keep the unbiased
  measurement. Existing templates were recomputed from their stored samples.
- **Phase 8 result (2026-09-25, TORGO headMic, seed 20260925, 40 probes per
  identity, 11 evaluation speakers: 5 control, 6 dysarthric; ADR 6
  protocol):** held-out spread lowered FRR at the fixed operating point from
  63.5% to 22.0% (control) and from 72.9% to 36.3% (dysarthric), while FAR rose
  from 0.25% to 1.75% (control) and from 0.00% to 0.83% (dysarthric). False
  accepts stay low, so `THRESHOLD_MARGIN` is unchanged and held-out spread
  stays. Margin-sweep EER is 6.7% (control) and 8.8% (dysarthric). Caveat: the
  corpus pools different words into one template, so every identity was below
  `COHESION_MIN`; a live template is five takes of one repeated sound. This is
  preliminary evidence on a small corpus, not a benchmark.

---

## 4. Interleaved enrollment

- **Date:** 2026-09-25
- **Status:** accepted
- **Context:** The first live checkout attempts failed often (3 of 8 takes
  passed) even though scoring and templates were verified correct. Each
  sound's 5 enrollment takes had been recorded back to back in about 15
  seconds, so the template and its held-out spread described one moment,
  not how the person varies. A second enrollment using words instead of a
  hum and a vowel reached higher cohesion (0.72 to 0.79 against 0.60 to 0.63)
  and passed, but with margins of only 0.02 to 0.03.
- **Decision:** Name all sounds first, then always record the sound with the
  fewest takes (ties in list order). Takes arrive in rounds (a, b, c, a, b,
  c, ...), so each sound is sampled at several moments across the session.
  The screen also recommends words or short phrases over hums and single
  vowels. No server change: the enrollment API already accepts takes for
  several sounds in any order. §7 parameters are unchanged.
- **Alternatives rejected:** (a) Loosen `THRESHOLD_MARGIN`: raises false
  accepts with no measurement of them yet (Phase 8). (b) Rely on adaptation
  (Phase 9) alone: it improves sounds that already pass, not one that never
  does. (c) Require multiple enrollment sessions on different days: more
  representative, but too much to ask of the people this is for.
- **Consequences:** Templates and thresholds reflect more realistic
  variation, which may lower some thresholds; Phase 8 measures the effect on
  false accepts. A re-record after low cohesion is still back to back,
  because only that sound remains. Existing enrollments keep their old
  templates until the person starts a sound over.

---

## 6. Speaker-disjoint evaluation cohorts and within-identity enrollment

- **Date:** 2026-09-25
- **Status:** accepted
- **Context:** Section 8.1 originally prohibited sharing speaker identities between enrollment and test, which makes genuine speaker verification trials impossible. Development and evaluation identities must be separate instead. The corpus has arbitrary utterances, not five repetitions of three personalized sounds.
- **Decision:** Reserve one third of each group (at least one identity) for development, with a deterministic seed. Evaluate the remaining identities using five enrollment recordings and up to 40 distinct probes each, preferring a different recording session. Use fixed existing thresholds without corpus tuning. Compare in-sample versus leave-one-out spread on identical trials. Group impostor rates by the claimed identity, using every other evaluation identity as an impostor. Report cohort sizes, exclusions, low cohesion, and session fallbacks. Keep low-cohesion templates in this diagnostic experiment, explicitly separate from the live passkey policy.
- **Alternatives rejected:** Disjoint enrollment/test identities cannot provide genuine trials. A random clip-level development/test split leaks identities. Claiming the corpus experiment validates the personalized sound challenge overstates the evidence. Choosing examples by scores cherry-picks results.
- **Consequences:** Preliminary text-independent speaker-verification evidence only. No live thresholds, replay behavior, or fallback policy changes. EER sweeps personal-threshold score margins; FAR/FRR use the unchanged operating point. ADR 3 remains provisional for live enrollment. ADR 5 is reserved for the unresolved high-value passkey-only fallback decision.
