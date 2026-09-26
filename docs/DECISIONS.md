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

## 1. Visa Intelligent Commerce mapping

- **Date:** 2026-09-26
- **Status:** accepted (mapping only; we have no Intelligent Commerce access, §9.1)
- **Context:** Visa Intelligent Commerce (VIC) is gated, so Timbre ships on Stripe test mode behind the `PaymentProvider` interface (§9.3). The Visa challenge scores platform fluency, so this records where Timbre would sit in VIC, using Visa's own capability names from its developer page (developer.visa.com/capabilities/visa-intelligent-commerce): **Tokenization**, **Authentication** ("step up verification of the cardholder and set up a Passkey that will be used to authenticate Payment Instructions"), **Payment Instructions**, and **Signals**.
- **Decision:** Position Timbre as an issuer-side step-up verification method inside VIC's Authentication capability, one that works for cardholders whose speech other voice checks reject, with the passkey as the fallback VIC already defines.

| Timbre step (code) | VIC capability | How it maps | Honest gap |
|---|---|---|---|
| Card tokenized at seeding; the issuer holds only a token reference and last four (`PaymentProvider.create_token`, `payment_tokens` table) | Tokenization | The same "no card number leaves the issuer" rule as a network token | Ours is a Stripe PaymentMethod, not a VIC agent-specific token |
| Voice approval: two of the person's own sounds, personal threshold, replay check (`issuer/approvals.py` `voice`) | Authentication: step-up verification of the cardholder | Timbre is a step-up method the issuer chooses, like a 3-D Secure challenge (ADR 2) | VIC does not publish a hook for issuer-defined step-up methods that we could find |
| Passkey fallback and step-up at or above $50 (`issuer/webauthn_routes.py`) | Authentication: Passkey set-up and use | Real WebAuthn passkeys, registered at the bank and asserted at checkout | Ours are our own WebAuthn credentials, not Visa Payment Passkeys |
| `instruction_id` created when the shopper confirms a cart, bound to the approval and sent with the authorization (`authorize(..., instruction_id)`, Stripe metadata) | Payment Instructions | One confirmed instruction per purchase; the authorization must carry it, so a verification cannot be reused for a different charge | No standing limits or categories; each instruction is a single cart |
| Outcome reported after settlement (`PaymentProvider.report_outcome`); the merchant learns only `{verified, transaction_id}` | Signals | The instruction plus the outcome is the record VIC uses for disputes | On Stripe the signal is only logged |

- **Alternatives rejected:** Claiming a VIC integration we do not have (§2.6). Building against guessed VIC endpoints (§13.3).
- **Consequences:** A `VisaProvider` would implement the same interface: `create_token` over Tokenization, `authorize` carrying the Payment Instruction, `report_outcome` over Signals, with Timbre's voice check as the Authentication step. The pitch line: "Timbre is the step-up method VIC's Authentication capability needs for cardholders whose speech other checks reject, and it falls back to the passkey VIC already specifies." Owner for the Devpost wording: integration and pitch role.

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

## 5. High-value purchases fall back to the passkey alone

- **Date:** 2026-09-26
- **Status:** accepted
- **Context:** At or above `STEP_UP_AMOUNT` ($50), a voice match still needs
  the passkey (voice AND passkey). The open question was what happens when
  both voice attempts fail on such a purchase: the passkey alone, or
  something stricter.
- **Decision:** Keep the existing behavior. After `MAX_VOICE_ATTEMPTS` (2)
  failed voice attempts, any purchase, including one at or above
  `STEP_UP_AMOUNT`, completes with the passkey alone. The session records
  `method='passkey'`. No §7 parameter changes. Locked by
  `test_step_up_purchase_falls_back_to_passkey_only_after_two_failures`.
- **Alternatives rejected:** (a) Block the purchase after two failures:
  violates §2.4 (never dead-end the user). (b) Require a second factor
  beyond the passkey (a one-time code, a call to the bank): adds an
  inaccessible step for the people this is for and is out of scope (§3.4).
  (c) Refuse large purchases for anyone whose voice fails: penalizes
  exactly the users whose speech varies day to day.
- **Consequences:** A passkey alone can approve a large purchase after two
  voice failures, so the passkey is the real security floor. Voice adds
  assurance above that floor and never removes access. The merchant still
  learns only `{verified, transaction_id}`.

---

## 6. Speaker-disjoint evaluation cohorts and within-identity enrollment

- **Date:** 2026-09-25
- **Status:** accepted
- **Context:** Section 8.1 originally prohibited sharing speaker identities between enrollment and test, which makes genuine speaker verification trials impossible. Development and evaluation identities must be separate instead. The corpus has arbitrary utterances, not five repetitions of three personalized sounds.
- **Decision:** Reserve one third of each group (at least one identity) for development, with a deterministic seed. Evaluate the remaining identities using five enrollment recordings and up to 40 distinct probes each, preferring a different recording session. Use fixed existing thresholds without corpus tuning. Compare in-sample versus leave-one-out spread on identical trials. Group impostor rates by the claimed identity, using every other evaluation identity as an impostor. Report cohort sizes, exclusions, low cohesion, and session fallbacks. Keep low-cohesion templates in this diagnostic experiment, explicitly separate from the live passkey policy.
- **Alternatives rejected:** Disjoint enrollment/test identities cannot provide genuine trials. A random clip-level development/test split leaks identities. Claiming the corpus experiment validates the personalized sound challenge overstates the evidence. Choosing examples by scores cherry-picks results.
- **Consequences:** Preliminary text-independent speaker-verification evidence only. No live thresholds, replay behavior, or fallback policy changes. EER sweeps personal-threshold score margins; FAR/FRR use the unchanged operating point. ADR 3 remains provisional for live enrollment. ADR 5 records the high-value passkey-only fallback decision.

---

## 7. Cheap accuracy candidates: none adopted

- **Date:** 2026-09-26
- **Status:** accepted (no live change)
- **Context:** The goal was higher accuracy and fewer false accepts without training (docs/RESEARCH.md). `make variants` scored 4 preprocessing variants (plain, silence trimming, multi-crop, both) times 7 scorers (centroid, top-2 per-sample, mean subtraction, AS-norm with k = 10, 30, 60, mean subtraction plus AS-norm) on the Phase 8 trials. Each configuration's margin was set on the 4 development speakers to match the live policy's development FRR (30.0%); the configuration with the lowest development EER was then checked once on the 11 evaluation speakers against plain plus centroid under the same calibration.
- **Decision:** Keep the live pipeline (plain embedding, centroid, held-out spread, `THRESHOLD_MARGIN`, `GLOBAL_FLOOR`). The development pick, multi-crop plus mean subtraction, failed all three checks on evaluation speakers: control FAR 1.75% to 2.30%, dysarthric FAR 0.83% to 0.88%, dysarthric FRR 36.25% to 41.25% (budget 2 points).
- **Evidence beyond the pick (shown for transparency, chooses nothing):** no configuration beat the reference's dysarthric EER of 8.75%. Configurations that lowered FAR in both groups (for example multi-crop plus AS-norm k = 10: 1.40% and 0.46%) raised dysarthric FRR by roughly 10 to 15 points. Silence trimming consistently hurt dysarthric speakers (for example FRR 36.25% to 49.17% with the centroid), plausibly because quiet dysarthric speech falls below a threshold set relative to the loudest frame.
- **Known flaw, disclosed:** on development speakers the cohort (for AS-norm and mean subtraction) is drawn from the same speakers who serve as impostors, so cohort-based methods look better on development than they are; that is why development chose mean subtraction. With 4 development speakers there is no disjoint cohort to use instead. The evaluation table shows that no configuration passes all three checks, so a cleaner selection would not have produced an adoption.
- **Alternatives rejected:** Picking the best-looking evaluation row (tuning on evaluation speakers, ADR 6). Loosening the FRR budget, which shifts the cost of fewer false accepts onto dysarthric users, the population the project exists for.
- **Consequences:** No template recompute, no threshold change, no latency change. The harness (`ml/preprocess.py`, `ml/variants.py`, `scripts/run_variants.py`) stays for future candidates. The remaining lever from the survey is a stronger or second embedding model (plan Phase 4), which needs a new dependency and a download; a larger development cohort (another corpus) would also make selection trustworthy. Preliminary, small corpus, correlated trials.

---

## 8. Candidate encoders and ECAPA fusion: not adopted yet; fusion is a lead

- **Date:** 2026-09-26
- **Status:** accepted (no live change); adoption of a fusion is an open decision for the team
- **Context:** Plan Phase 4 (docs/RESEARCH.md §3). `make models` compared four pretrained VoxCeleb encoders, WeSpeaker CAM++ (Apache-2.0), ResNet221-LM (Apache-2.0), ResNet34-LM (CC-BY-4.0) as ONNX, and SpeechBrain ResNet (Apache-2.0), alone and fused with ECAPA (equal-weight cosine averaging), each with the live centroid scorer and a floor-free variant. Same protocol as ADR 7: margins matched on 4 development speakers to the live development FRR (30.0%), the lowest development EER picked, checked once on 11 evaluation speakers. No new pip dependency: onnxruntime was already installed by faster-whisper, fbank comes from the pinned torchaudio.
- **Decision:** Keep ECAPA alone live. The development pick, ResNet221 with the centroid, lowered FAR in both groups (control 1.75% to 0.80%, dysarthric 0.83% to 0.25%) but raised dysarthric FRR from 36.25% to 45.42%, beyond the 2-point budget.
- **Lead (post hoc, chooses nothing):** fusing ECAPA with a second encoder helped fairly consistently. Three of the four fusions with the centroid lowered EER in both groups (control 6.60% to 4.90% to 5.15%; dysarthric 8.75% to 5.67% to 6.67%); the fourth, ECAPA + CAM++, lowered dysarthric EER but raised control EER to 7.00%. Several would have passed all three checks; for example ECAPA + ResNet34: control FAR 1.05%, dysarthric FAR 0.50%, dysarthric FRR 33.75%, with 57 ms extra per take. The development ranking did not predict evaluation (ResNet221 had the best development EER and among the worst dysarthric evaluation EER), which confirms that 4 development speakers cannot choose.
- **Latency per take (CPU, this laptop):** CAM++ 53 ms, ResNet34 57 ms, ResNet221 276 ms, SpeechBrain ResNet about 2.7 s (disqualified by the 2 s target).
- **Alternatives rejected:** Adopting ECAPA + ResNet34 now on evaluation numbers (tuning on evaluation speakers, ADR 6). Relaxing the FRR budget for ResNet221.
- **Consequences:** Nothing changes live. To adopt a fusion honestly, confirm it on data it was not chosen on: a second dysarthric corpus (for example UA-Speech, which needs a license request) or real enrollments. If the team adopts ECAPA + ResNet34 anyway, record it as a post-hoc choice, credit the CC-BY-4.0 model, move the encoder into ml/encoder.py (§6), recompute templates from stored samples, and retune `GLOBAL_FLOOR` and `THRESHOLD_MARGIN` for the fused scale.

---

## 9. Fusion rejected on independent data; the live design holds on EasyCall

- **Date:** 2026-09-26
- **Status:** accepted
- **Context:** ADR 8 left ECAPA + ResNet34 fusion as a lead chosen post hoc. It was tested once on EasyCall (Italian dysarthric command corpus, 30 evaluation speakers) under docs/PREREGISTRATION.md and Amendment 1, both committed before any EasyCall score existed.
- **Decision:** Keep ECAPA alone. Fusion failed the pre-registered rule (worse control EER, higher FAR in both groups); see the Outcome section of docs/PREREGISTRATION.md.
- **What the same run showed about the live configuration:** with the product's own protocol (five takes of one repeated command, the rest as probes from other sessions) and the live policy, ECAPA reached EER 0.29% (control) and 2.43% (dysarthric); at a margin of 0.119, FAR 0.02% and 0.23% with FRR 4.40% and 7.95%. Against the tougher same-word attacker (exploratory, not pre-registered): dysarthric EER 2.84%, FAR 0.63%, FRR 7.30% at the live margin. The text-independent check on the same speakers gave 8.75% dysarthric EER, the same as TORGO, which supports designing enrollment around a repeated personal sound.
- **Alternatives rejected:** Adopting fusion on its single passing sub-check (dysarthric EER). Re-running with other encoders or margins on EasyCall (the pre-registration forbids it).
- **Consequences:** No live change. The numbers that may be quoted, always with these caveats: one corpus, Italian, 8 kHz audio upsampled, corpus impostors rather than trained imitators or synthetic voices, correlated trials, not a population claim, and the same-word figures are exploratory. The fusion code stays for reproducibility. UA-Speech (with a UIUC license) or real enrollments remain the next independent checks.

---

## 10. Agentic shopping asks only when a wrong guess changes what is bought

- **Date:** 2026-09-26
- **Status:** accepted (supersedes the Feature 3 policy that every supplied field is confirmed)
- **Context:** A live spoken request took five separate confirmations before reaching the cart, including values heard clearly. For people with dysarthria every extra turn is costly, and the purchase is already protected downstream: nothing is bought until checkout, the issuer challenge, and payment.
- **Decision:** Accept high-confidence values without asking. Require only the product. Default an unstated quantity to 1 and an unstated budget to no limit, and show both assumptions. Ask one Yes/No question for each medium or low value or model-flagged material ambiguity, at most one per field and per span of words. Propose a store brand for a heard word that sounds like one, never accept it without a Yes, and set the same words aside elsewhere. Ignore a store brand the speaker never said. Apply a resolved request straight to the cart, with Undo and cart review as the confirmation step.
- **Alternatives rejected:** (a) Keep confirming every field: the failure being fixed. (b) One summary confirmation before adding to the cart: still an extra turn on every request, and the cart already is a reviewable summary that costs nothing to undo. (c) Let the model pick a catalog product ID directly: harder to verify, and the deterministic ranking keeps selection auditable and testable. (d) Auto-accept brand repairs: a wrong brand silently changes the product, so a mishearing is still asked about once.
- **Consequences:** Most clear requests need zero questions (live: of 11 shopping transcripts, 8 needed no question and 3 needed one). Correctness of silent acceptance depends on the model's confidence labels, bounded by deterministic guards (inferred brands ignored, one question per span, catalog-only brand proposals). The merchant/issuer boundary and every checkout safeguard are unchanged.
