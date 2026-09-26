# Change Log

Part of the Timbre instruction set. Read `CLAUDE.md` first.
**Every edit to this repository gets an entry here. No exceptions.**

---

## 14. Change Log: APPEND ON EVERY EDIT

**Format.** Newest entry at the top. Every entry, no matter how small:

```
### YYYY-MM-DD HH:MM - <short title>
- **Files:** path/one.py, path/two.jsx
- **What:** what actually changed
- **Why:** the reason, in one sentence
- **Verify:** the exact command or click-path that confirms it works
- **Risk/Notes:** anything left broken, stubbed, or assumed
```

If a change alters a §7 parameter, an architectural boundary in §5.1, or a
non-negotiable in §2, **also** add an entry to `docs/DECISIONS.md` recording the
alternatives considered and why they were rejected.

---

### 2026-09-26 08:30 - Storefront redesign with purposeful motion

- **Files:** web/src/pages/{Shop,Checkout,Receipt}.jsx, web/src/components/{SiteHeader,VoiceShopping,CartDrawer,Icons}.jsx, web/src/components/ProductCard.jsx (new), web/src/components/jump.js (new), web/src/styles.css, web/src/styles/checkout.css. Built by two helper agents in parallel with strict file ownership, then integrated and reviewed.
- **What:** A teal "market band" hero whose content is the voice shopping panel; aisle chips that jump to and focus each section; a 2/3/4/5-column grid of bordered product cards with image fade-in, computed unit prices, an "In cart: N" badge, and an Add button that becomes a quantity stepper; a sticky 64px header with a scroll-linked shadow and a cart badge that bumps on adds; a slide-over cart drawer with a free-delivery meter (threshold from the quote), pill steppers, and a pinned footer; a checkout with a step list and a sticky order summary (summary first on phones, items in a details element); a centered receipt with a drawn check mark and the two-key approval response as a code card. Motion follows the brief's 17-item spec plus a one-time staggered grid entrance, image zoom inside its well on hover (cards never lift), and a pulsing ring on the microphone while recording.
- **Why:** User asked to elevate the storefront with animations, grounded in how real grocery stores look (brief: Whole Foods, Weee, Misfits Market, Instacart tokens, Baymard, NN/g, WCAG 2.3.3).
- **Verify:** `npm --prefix web run build`; `make test` (131 passed). Browser QA at 1440, 900, and 375px: no horizontal scroll, no console errors, header exactly 64px, Add focuses the stepper's plus, the badge bumps, the drawer meter reads "Add $26.42 more for free delivery" at an $8.58 subtotal, the empty drawer hands focus to "Speak an item", checkout and receipt render, Baseline and Dashboard unaffected. A stylesheet audit found no movement outside `prefers-reduced-motion: no-preference`.
- **Risk/Notes:** Fixed during QA: the cart button made the header 72px (sticky chips would tuck under it); the drawer said "ships free" when the quote lacked a threshold (it now hides the meter instead); keyboard focus fell to the body after answering a voice suggestion (it now returns to "Speak an item"); the checkout step connector dangled when wrapping at phone width; dead drawer and checkout rules removed from styles.css. The "$35" in the hero fact pill is a second copy of `FREE_SHIPPING_MIN_CENTS` (the catalog response carries no threshold). An independent accessibility review is in progress.

---

### 2026-09-26 07:30 - Storefront redesign foundation (tokens, motion rules, research)

- **Files:** web/src/styles.css (tokens, reduced-motion rule), web/src/styles/checkout.css (new, empty), web/src/main.jsx, web/src/components/Icons.jsx (Mic, Trash), api/checkout.py (`/cart/quote` returns `free_shipping_min_cents`), design-system/seaside-market/MASTER.md (overrides 1 and 7 revised).
- **What:** Groundwork for the storefront redesign from a researched brief (Whole Foods, Weee, Misfits Market, Instacart design tokens, Baymard, NN/g, WCAG 2.3.3): warm sand background, kelp-teal hero band, tint, skeleton, three shadow levels, radius and motion tokens, all with computed contrast ratios. The reduced-motion rule now stops all movement but keeps fades, which WCAG 2.3.3 does not count as motion. The quote endpoint exposes the free-delivery threshold so the drawer meter has one source of truth.
- **Why:** User asked to elevate the storefront UI with animations; the shared pieces are laid first so two builders can work in parallel without editing the same files.
- **Verify:** `make test` (131 passed); `npm --prefix web run build`.
- **Risk/Notes:** Design overrides 1 ("no hero") and 7 ("only 180ms color transitions") are revised on purpose. The bank widget's tokens are untouched.

---

### 2026-09-26 07:00 - Demo hardening: rehearsal, executable demo script, Devpost draft

- **Files:** docs/DEVPOST.md (new, drafted by a helper agent and reviewed), docs/DEMO.md, docs/CONTEXT.md (§16 steps 2 and 5).
- **What:** Rehearsed the backend end to end with real dysarthric corpus audio (EasyCall speaker m09 enrolled as the demo user through the bank API): `make reset` works on Windows; one sound was flagged for low cohesion and replaced, as designed; a voice approval verified (scores 0.771 and 0.823 against thresholds 0.709 and 0.615) in 559 ms of server verification, a real Stripe test PaymentIntent was captured, and the merchant received exactly `{verified, transaction_id}`; a same-word impostor attempt was rejected (0.337 and 0.457) and the merchant saw `verified: false`. In the browser, the widget asked Maya for her two enrolled sounds with no console errors. DEMO.md step 2 now uses the Baseline page (the widget cannot take a corpus clip), lists one-time prerequisites and live enrollment after every reset, and adds warm-up, sound-choice, and timing notes. CONTEXT §16 no longer says "simulated months". DEVPOST.md is a ready-to-paste draft with every number and caveat traceable to README, ADR 3, ADR 9, and the pre-registration.
- **Why:** Phase 10 demo hardening.
- **Verify:** Follow docs/DEMO.md; the rehearsal numbers above come from a scratch script run against `make issuer` and `make api`.
- **Risk/Notes:** Still needs a human: a real microphone enrollment and approval, a Windows Hello passkey, and the backup video. One unexplained page reload on the first browser run after startup; not reproduced. The full voice response is about 2.6 s because it includes Stripe; "Checked in X seconds" shows the verification alone.

---

### 2026-09-26 06:20 - README reflects what is built and measured

- **Files:** README.md.
- **What:** Replaced the "in progress" status with the problem statement, what works, a table of measured claims each tied to its ADR and caveats, run instructions, and full credits (TORGO, EasyCall CC BY-NC 2.0, ECAPA, the candidate encoders not used live, Whisper for store-side shopping only).
- **Why:** Phase 10; the README is what judges read first, and §2.6 requires every claim to be one we can back.
- **Verify:** Each number in the table matches ADR 3, 9, the baseline and drift outputs; the novelty framing matches docs/CONTEXT.md §11.
- **Risk/Notes:** Devpost text is still to be written from this.

---

### 2026-09-26 06:10 - EasyCall confirmation: fusion rejected, live design holds (ADR 9)

- **Files:** docs/PREREGISTRATION.md (Outcome), docs/DECISIONS.md (ADR 9), docs/RESEARCH.md, AGENTS.md, scripts/run_same_word.py (new, exploratory), .gitignore.
- **What:** Ran `make confirm` once as pre-registered. ECAPA + ResNet34 failed 3 of 5 checks, so ECAPA stays alone and the fusion lead is closed. The live configuration measured, on 30 independent evaluation speakers with the product's repeated-sound protocol: EER 0.29% control and 2.43% dysarthric (FAR 0.02% and 0.23%, FRR 4.40% and 7.95%). An exploratory same-word attacker rescoring gave dysarthric EER 2.84%, FAR 0.63%, FRR 7.30% at the live margin.
- **Why:** The recommended path from ADR 8: confirm on data the configuration was not chosen on.
- **Verify:** `make confirm` (about 40 minutes the first time; cached after), then `python -m scripts.run_same_word`; compare with the Outcome table in docs/PREREGISTRATION.md.
- **Risk/Notes:** Caveats in ADR 9 travel with every number: one Italian corpus, 8 kHz upsampled, corpus impostors only, correlated trials. The same-word figures are exploratory. EasyCall is CC BY-NC 2.0 and stays under gitignored data/.

---

### 2026-09-26 05:45 - ADR 1: Visa Intelligent Commerce mapping

- **Files:** docs/DECISIONS.md (ADR 1).
- **What:** Replaced the stub with a mapping from each Timbre step, with its code location, to VIC's published capabilities (Tokenization, Authentication with step-up verification and passkeys, Payment Instructions, Signals), with an honest gap column for each row.
- **Why:** Phase 10 and §9.2: platform fluency is scored, and the Devpost needs this without claiming an integration we do not have.
- **Verify:** Read ADR 1; capability names and quotes match developer.visa.com/capabilities/visa-intelligent-commerce (checked 2026-09-26).
- **Risk/Notes:** No VIC access; every row states its gap. Devpost wording still to be written by the pitch owner.

---

### 2026-09-26 05:30 - Keyword fallback no longer suggests from one shared word

- **Files:** api/llm.py (`words`, `keyword_match`), api/config.py (`KEYWORD_MIN_QUERY_COVERAGE`, `FILLER_WORDS`), tests/test_shopping.py.
- **What:** Found in a live check: typing "whole milk" (not in the catalog) suggested "21 Whole Grains and Seeds Bread", and "cheddar" was matched confidently to one of three cheddar products. Now a product must explain more than half of the query's content words (brand words count, fillers such as "please" do not, plurals and accents are folded), and any other product covering the query as fully makes the answer a yes/no repair rather than a confident pick.
- **Why:** The fallback runs whenever no LLM key is set, which is the current state; a wrong confident suggestion is the failure this user already lives with.
- **Verify:** `make test` (shopping tests cover "whole milk", brand, plural, accent, and the cheddar tie); live: `curl -X POST localhost:8000/shopping/text -d '{"text":"whole milk"}'` returns no product. Browser: typing "cheddar" asks "Did you mean ...?"; the bank widget's readback said "Pay $10.45 to seaside market with your Travel Mastercard ending 4 4 4 4." (headless Chromium, no console errors).
- **Risk/Notes:** Stricter matching means a few more "I could not find one item" answers; the product buttons and typing remain.

---

### 2026-09-26 05:00 - Spoken confirmation, split along the privacy boundary (§10.3)

- **Files:** web/src/lib/speak.js (new), web/src/issuer/speak.js (new), web/src/components/VoiceShopping.jsx, web/src/issuer/ApprovalWidget.jsx, docs/ALGORITHM.md (§10.3 as built), docs/DEMO.md.
- **What:** After a spoken shopping request, the store reads its suggestion aloud ("Add ... for $4.99?") and offers "Say it again"; typed requests stay silent. The bank widget offers "Read this payment aloud": amount, store, and, once a card is chosen, its nickname and last four read digit by digit. Speech stops before either microphone opens and on close, so a readback is never recorded.
- **Why:** Demo step 3 and §10.3. The issuer never sees items and the store never sees the card (ADR 2, §2.5), so each side reads what it already shows; a fixed template cannot misstate a number, which is what §10.3's no-arithmetic rule was protecting.
- **Verify:** `npm --prefix web run build`; `make test` (guard tests keep each side's helper in its own folder). In a browser: speak an item on the Shop page and hear the suggestion; at checkout press "Read this payment aloud".
- **Risk/Notes:** Uses the browser's speech synthesis (no network, no LLM); the button is hidden where it is unavailable. Deviation from §10.3's LLM-composed wording, recorded in ALGORITHM.md.

---

### 2026-09-26 04:30 - Pre-registration amendment 1 (before scoring)

- **Files:** docs/PREREGISTRATION.md.
- **What:** Declared, before any embedding or score existed: upsampling of EasyCall's 8 kHz audio to 16 kHz for both configurations, exclusion of the one speaker without a severity label, and using every eligible command as its own template so P1 has about 1,390 genuine trials instead of about 44.
- **Why:** The metadata showed one take per command per session, which would leave the pre-registered test with almost no statistical power.
- **Verify:** `git log -- docs/PREREGISTRATION.md` shows this amendment precedes the confirmation run.
- **Risk/Notes:** Configurations, split, calibration, and the adoption rule are unchanged.

---

### 2026-09-26 04:10 - Pre-register the fusion confirmation on EasyCall

- **Files:** docs/PREREGISTRATION.md (new).
- **What:** Froze the hypothesis, configurations (ECAPA versus ECAPA + ResNet34), corpus (EasyCall, CC BY-NC 2.0), speaker split, text-dependent protocol, calibration, and a three-part adoption rule, before downloading or scoring any EasyCall audio.
- **Why:** ADR 8's fusion lead came from post-hoc evaluation numbers; the recommended path is to confirm it on data it was not chosen on, and committing the rule first makes the test honest.
- **Verify:** `git log -- docs/PREREGISTRATION.md` shows this commit precedes any EasyCall result.
- **Risk/Notes:** UA-Speech mirrors on the Hub carry no license and the official corpus needs a UIUC agreement, so UA-Speech is not used.

---

### 2026-09-26 03:40 - Candidate encoders and ECAPA fusion (ADR 8: not adopted; fusion is a lead)

- **Files:** ml/candidate_encoders.py (new), scripts/warm_candidates.py (new), scripts/run_variants.py (`--suite models`, fusion, per-model timing), ml/variants.py (`FreeCentroid`), tests/test_variants.py (fbank front end), tests/test_guards.py (issuer never loads candidates), Makefile (`models`), .gitignore, docs/DECISIONS.md (ADR 8), docs/RESEARCH.md, AGENTS.md.
- **What:** Compared WeSpeaker CAM++, ResNet221-LM, ResNet34-LM (ONNX) and SpeechBrain ResNet, alone and fused with ECAPA, under the ADR 7 protocol. The development pick (ResNet221) halved FAR but raised dysarthric FRR from 36.25% to 45.42%, so ECAPA stays alone live. Post hoc, 3 of 4 ECAPA fusions lowered EER for both groups; ECAPA + ResNet34 would have passed every check at 57 ms extra per take. Recorded as a lead needing independent data.
- **Why:** Plan Phase 4, requested by the user.
- **Verify:** `python -m scripts.warm_candidates` (about 220 MB into models/candidates/); `make models`; read `docs/models_results.md`. `make test` passes.
- **Risk/Notes:** No new pip dependency: onnxruntime (already installed by faster-whisper) is used directly, so pin it in requirements.txt if a candidate is ever adopted. Candidates are evaluation-only and a guard test keeps them out of the issuer. SpeechBrain ResNet takes about 2.7 s per take and is disqualified for live use. ResNet34 is CC-BY-4.0 (attribution needed if adopted).

---

### 2026-09-26 02:30 - Accuracy research and candidate comparison (ADR 7: none adopted)

- **Files:** docs/RESEARCH.md (new), docs/DECISIONS.md (ADR 7), docs/CONTEXT.md (§11), ml/preprocess.py (new), ml/variants.py (new), scripts/run_variants.py (new), tests/test_variants.py (new), issuer/config.py (candidate constants), Makefile (`variants`), .gitignore, AGENTS.md.
- **What:** Surveyed published work on improving speaker verification and lowering false accepts (docs/RESEARCH.md, with sources). Built `make variants`: 4 preprocessing variants (plain, energy-based silence trimming, multi-crop, both) times 7 scorers (centroid, top-2 per-sample, mean subtraction, AS-norm k = 10/30/60, mean subtraction plus AS-norm) on the Phase 8 trials, margins calibrated on development speakers to the live policy's development FRR, one development-chosen configuration checked on evaluation speakers. Result: the pick (multi-crop plus mean subtraction) raised FAR in both groups and dysarthric FRR by 5 points, so nothing is adopted; no configuration beat the live dysarthric EER of 8.75%, and trimming hurt dysarthric speakers.
- **Why:** User asked for research into higher accuracy and fewer false positives; the plan required measuring before changing the live path.
- **Verify:** `make test` (123 passed); `make eval && make variants`, then read `docs/variants_results.md` (embeddings cached under `data/variant_cache/`; first run about 30 minutes, reruns about 2).
- **Risk/Notes:** No live behavior changed; the new constants are marked evaluation-only. Disclosed flaw: with 4 development speakers, cohort-based scorers' cohorts overlap development impostors, which flatters them on development (ADR 7). Next levers: a larger development cohort from another corpus, then a stronger or second embedding model (plan Phase 4, new dependency).

---

### 2026-09-26 00:40 - Baseline page, Phase 9 adaptation, Dashboard drift chart

- **Files:** issuer/verification.py (`adapt`), issuer/approvals.py, issuer/config.py (`BASELINE_MAX_WER`), ml/baseline_asr.py (new), ml/constants.py (`WHISPER_DIR`), api/config.py, api/asr.py, scripts/run_baseline.py (new), scripts/run_drift.py (new), web/src/pages/{Baseline,Dashboard}.jsx (new), web/src/{App.jsx,lib/router.js,styles.css}, Makefile (`baseline`, `drift`), .gitignore, docs/DEMO.md, AGENTS.md, tests/test_{baseline,verification,challenge,shopping}.py.
- **What:**
  - Phase 9: `adapt()` implements §7.4 (confident-pass gate, ALPHA step, bisection clamp to `MAX_DRIFT`). The voice handler adapts only a matched attempt, guards the template write against a concurrent change, and fills `verifications.drift` (the column already existed). With current constants a confident pass moves a template about 0.006 at most, so the clamp is a backstop; tests force it with a larger step.
  - Baseline page (`#/baseline`, `make baseline`): a transcription check (Whisper small, pass if word error rate <= 25%) and Timbre scored on the identical Phase 8 takes. Result: dysarthric speakers pass the transcription check 45.2% of the time and Timbre 63.6%; control 83.0% and 78.0%. The transcription check accepts other speakers' clear takes about 60 to 64% of the time, Timbre 0.8 to 1.8%. Per speaker it is mixed (M01, M02, M04 much better with Timbre; F03 worse), and the page shows that. Examples are chosen by a disclosed rule, and one garbled corpus prompt is excluded.
  - Dashboard (`#/dashboard`, `make drift`): 6 cross-session speakers; the same 120 later takes each against a static and an adaptive template. Own takes accepted: 65.9% static, 84.1% adaptive; the static template decays over later takes while the adaptive one rises. Other speakers accepted against final templates: 1.46% static, 1.96% adaptive (2400 trials).
  - Voice shopping n-best keeps only distinct wordings (beams differed mostly by case and punctuation).
- **Why:** Next items in the Handoff: the §3.1 baseline MVP screen and Phase 9 with its drift chart.
- **Verify:** `make test` (109 passed); `npm --prefix web run build`; `make eval && make baseline && make drift`, then open `#/baseline` and `#/dashboard` (checked in a headless browser; no console errors besides the junction font issue below, since fixed).
- **Risk/Notes:** `MAX_DRIFT` bounds each update, not the total: templates drifted 0.18 to 0.32 in cosine over 37 to 87 updates. Impostor acceptance rose by 0.5 points. This is disclosed on the Dashboard; whether a cumulative cap is needed is an open question. TORGO sessions are days apart, not months, and the page says so. Baseline and drift outputs (including corpus audio clips) are generated locally and gitignored; run the three make targets on each demo machine (about 25 minutes, mostly Whisper). The issuer must be restarted to pick up adaptation. `web/node_modules` in this clone is now a real install (a junction made Vite refuse to serve fonts with 403).

---

### 2026-09-25 23:55 - Phase 8 run on Windows; voice shopping encoder fix

- **Files:** api/asr.py, web/src/lib/shoppingRecorder.js, tests/test_shopping.py, docs/DECISIONS.md (ADR 3 result), AGENTS.md (Handoff); generated and ignored: docs/eval_results.{md,json}, docs/eval_roc.png.
- **What:** (1) `asr.hypotheses()` passed a short mel window straight to the Whisper encoder, which accepts exactly 3000 frames, so every real voice request would have failed and returned "Voice shopping is unavailable". It now pads with faster-whisper's `pad_or_trim`, as `WhisperModel.transcribe` does. A new test feeds a 2 s clip through a fake model and asserts the encoder receives (80, 3000); without the fix it received (80, 201). (2) The shopping recorder trims a take to `MAX_SECONDS`, because the auto-stop timer fires a few milliseconds late and the merchant rejected any take over 10 s with a 400. The too-short message no longer says "Hold the sound" (enrollment wording). (3) Ran `make eval`: 15 headMic speakers, 7570 usable clips, 4 development and 11 evaluation identities, 675 clips embedded in 184 s. Results recorded in ADR 3: held-out spread cuts FRR by about half at a FAR cost below 2%; EER 6.7% control, 8.8% dysarthric.
- **Why:** Continuing Codex's Phase 7 and Phase 8 work on the Windows machine; the evaluation had not yet been executed.
- **Verify:** `make test` (96 passed); `npm --prefix web run build`; `make eval` then read `docs/eval_results.md`.
- **Risk/Notes:** The live Whisper path is still unexercised: `models/whisper-small` is not cached here (run `.venv/Scripts/python.exe -m scripts.warm_asr` on good wifi, about 480 MB), and `LLM_API_KEY` is empty, so reranking falls back to keywords and the on-vs-off intent-accuracy delta is unmeasured. Every evaluation identity was below `COHESION_MIN` because the corpus pools different words; that is a property of the corpus protocol, not of live enrollment. This clone's `.venv`, `data/`, `models/`, and `web/node_modules` are directory junctions to the older `../Timbre` clone (all gitignored).

---

### 2026-09-25 23:30 - Merchant voice shopping and constrained reranking

- **Files:** api/{asr,llm,shopping}.py, api/{config,main}.py, scripts/warm_asr.py, web/src/components/VoiceShopping.jsx, web/src/lib/{shoppingRecorder.js,api.js}, web/src/pages/Shop.jsx, web/src/styles.css, tests/test_shopping.py.
- **What:** Added merchant-only Whisper small beam n-best (via the pinned faster-whisper CTranslate2 decoder), local model warmup script, constrained Anthropic/Gemini JSON reranking, deterministic keyword fallback, and shopping text/audio endpoints. Added tap-to-record UI with explicit yes/no item confirmation, keyboard text fallback, cancellation, unmount cleanup, quantity limits, and live status announcements. No suggestion mutates the cart until confirmed.
- **Why:** Phase 7 follows the Phase 8 evaluation in the Handoff. The issuer must remain ASR-free and the merchant must not receive bank audio or identity details.
- **Verify:** `make test`; `npm --prefix web run build`; `.venv/bin/python -m scripts.warm_asr`; use Shop by voice or type an item and confirm it. Tests cover malformed/hallucinated/nonfinite LLM output, timeout fallback, and audio validation.
- **Risk/Notes:** Existing dependencies only. Model download is explicit; absent model returns an actionable typing fallback. No LLM key is configured here, so live provider calls and a measured reranking accuracy delta still require validation. Card details remain bank-side. Recorder code is deliberately separate from the issuer module to preserve its import boundary. API references checked: platform.claude.com/docs/en/models/overview and ai.google.dev/api/generate-content; decoder signature inspected from installed CTranslate2.

---

### 2026-09-25 23:10 - Phase 8 evaluator and reproducible Mac setup

- **Files:** ml/evaluate.py, scripts/run_eval.py, tests/test_evaluation.py, issuer/config.py, docs/ALGORITHM.md, docs/DECISIONS.md, docs/EVALUATION.md, .gitignore; local ignored .venv/, web/node_modules/, models/, data/.
- **What:** Implemented deterministic headMic evaluation, speaker-disjoint cohorts, disjoint enrollment/probes with cross-session preference, exact tied-score ROC and interpolated EER, fixed-policy FAR/FRR, in-sample versus held-out spread, JSON protocol audit and ROC/report output. Added abstract-vector metric/protocol tests. Installed the existing pinned Python and npm requirements and cached ECAPA/TORGO on this Mac. Corrected ADR 3's threshold-margin direction and clarified the impossible enrollment/test speaker separation in section 8.1 via ADR 6.
- **Why:** The Handoff's first priority was Phase 8; this fresh Mac clone lacked the prior Windows environment and ignored caches.
- **Verify:** `.venv/bin/python -m pytest -q tests/test_evaluation.py`; `make test`; `make eval`; `npm --prefix web run build`. Results will be recorded in the final handoff entry after execution.
- **Risk/Notes:** No live algorithm constants changed. This is a text-independent corpus diagnostic, not the full personalized-sound payment flow. Generated metrics remain provisional, with low-cohesion identities and quality exclusions disclosed. No new dependency, credential, audio, or database is tracked.

---

### 2026-09-25 22:30 - Handoff to Codex: CLAUDE.md becomes AGENTS.md

- **Files:** AGENTS.md (renamed from CLAUDE.md, plus a Handoff section at the top), CLAUDE.md (now the single line `@AGENTS.md`), README.md
- **What:** Followed the portability note: the guide is now AGENTS.md, which Codex reads; CLAUDE.md imports it, so Claude Code still works. The Handoff section lists what to read first, what is done (Phases 0-6), the next steps in order, open decisions, unverified items, and Windows environment quirks, and tells Codex to summarize done/next for the person running it. README status and pointers updated.
- **Why:** The project moves to Codex.
- **Verify:** `cat CLAUDE.md` prints `@AGENTS.md`; AGENTS.md starts with the Handoff section.
- **Risk/Notes:** Section numbers are unchanged, so references like "§2.5" still resolve. Codex does not read CLAUDE.md; keep AGENTS.md as the single source.

---

### 2026-09-25 22:10 - Phase 5: Stripe test-mode payments

- **Files:** issuer/payments/stripe_provider.py (new), issuer/payments/__init__.py, issuer/approvals.py, scripts/seed_demo.py, tests/conftest.py; `.env` (gitignored, not committed)
- **What:** `StripeProvider` implements the §9.3 interface: `create_token` attaches a Stripe named test PaymentMethod to a new Customer and stores the reference "cus_...:pm_..."; `authorize` places a manual-capture, off-session PaymentIntent; `capture` completes it and cancels the authorization if capture fails (closing the Phase 1 TODO without changing the interface); card declines return a clean `AuthResult(ok=False)`, while network or authentication errors are raised. It refuses any key that is not `sk_test_`. `get_provider()` now returns Stripe when a key is set and keeps the FakeProvider (with its loud STUB warning) only when there is none. `make seed` re-tokenizes existing fake tokens in place, so voice enrollments and passkeys survive the switch. The test suite pins an empty key, so tests never call Stripe.
- **Why:** Plan Phase 5. The user supplied a Stripe test key.
- **Verify:** `make seed` re-tokenized both demo cards (Visa 4242, Mastercard 4444). Live against Stripe test mode: authorize and capture of $1.00 returned `succeeded 100 usd`, `livemode = False`; a card that attaches but fails at charge (`pm_card_chargeCustomerFail`) returned a clean `card_declined`. The issuer log shows no FakeProvider warning. `make test` (81 passed).
- **Risk/Notes:** The key was shared in the chat transcript; it is test mode (no real money), but rolling it after the event is advisable. `pm_card_visa_chargeDeclined` is declined at attach time, not charge time, so it cannot be used to test the checkout decline path. Stripe calls now depend on network access; with no network, empty the key to fall back to the FakeProvider.

---

### 2026-09-25 21:55 - Phase 6: real passkeys (WebAuthn)

- **Files:** issuer/webauthn_routes.py (new), issuer/approvals.py, issuer/config.py, issuer/db.py, issuer/main.py, web/src/issuer/{ApprovalWidget.jsx,EnrollPage.jsx,issuerApi.js}, tests/softauthn.py (new), tests/test_passkeys.py (new), tests/test_boundary.py, tests/test_challenge.py, tests/test_guards.py
- **What:** The passkey STUB is gone. Registration (`/v1/passkeys/{user}/register/options` and `/verify`) and checkout assertions (`/v1/sessions/{id}/passkey/options` and `/passkey`) are verified with py_webauthn against `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN`. Challenges live in a new `webauthn_challenges` table, are single-use (deleted before verification) and expire after `WEBAUTHN_CHALLENGE_TTL_SECONDS`. The signature counter is stored and checked, so a cloned authenticator is rejected. The bank app gains a "Passkey backup" section (Windows Hello, phone, or security key). The widget calls the device's own passkey prompt; if the card has no passkey yet it explains that, links to the bank app in a new tab, and keeps the request open ("I have set it up. Try again"), so it is not a dead end.
- **Why:** Plan Phase 6: the §7.6 fallback and the step-up second factor must complete a real purchase.
- **Verify:** `make test` (81 passed). tests/softauthn.py is a software authenticator producing real P-256 WebAuthn responses; tests/test_passkeys.py covers register-then-pay, a phishing origin rejected, single-use challenges, no-passkey routing, a replayed assertion, a cloned authenticator caught by the counter, another card's passkey refused, and a tampered signature (nothing charged). The earlier boundary and challenge tests now complete payments with real assertions. Browser: the bank page is a secure context with `PublicKeyCredential` available and renders the passkey section with no console errors.
- **Risk/Notes:**
  - Not yet verified with a physical device prompt: the headless browser's CDP allowlist has no WebAuthn domain, so no virtual authenticator. Test with Windows Hello at `#/bank/enroll/maya`, then at checkout.
  - User verification (PIN or biometric) is preferred, not required, because some people cannot use either; device presence is always required.
  - STUB: passkey registration has no authentication, like enrollment; a real deployment puts it behind the bank's login.
  - New table `webauthn_challenges` (created automatically; no reset). `@simplewebauthn/browser` is now allowed in `web/src/issuer/` by the guard test (third-party, not storefront code).

---

### 2026-09-25 21:45 - Interleaved enrollment (ADR 4)

- **Files:** web/src/issuer/EnrollPage.jsx, docs/DECISIONS.md (ADR 4)
- **What:** Enrollment now asks for all sound names first, then always records the sound with the fewest takes, so takes come in rounds across the session instead of five in a row. The screen shows "Round N of 5: your X sound", announces the next sound after each take, and recommends words or short phrases over hums. Named-but-unrecorded sounds can be removed without a server call. Also fixed the same double-tap race the Phase 4 review found in the widget: the record button's guard now uses refs, so a quick double-tap cannot open two recordings.
- **Why:** Live results: back-to-back takes produced templates that described one moment, and genuine checkout takes failed (see the 21:20 entry). Chosen by the user (option A).
- **Verify:** `npm --prefix web run build` passes; guard tests pass. With a temporary user whose sounds had 2, 1, and 1 takes, the page asked for "Round 2 of 5: your bravo sound" (fewest takes, first in order). Then: Start over each sound at `#/bank/enroll/maya`, enroll in rounds, and check out.
- **Risk/Notes:** No server change. Existing templates stay as they are until a sound is started over. A re-record after low cohesion is still back to back (only one sound remains).

---

### 2026-09-25 21:20 - Phase 4 review fixes, and the first live results

- **Files:** issuer/approvals.py, web/src/issuer/ApprovalWidget.jsx, tests/test_challenge.py
- **What:** Security review: (1) a payment now stays with the first card chosen; switching to another card and back had re-rolled the challenge for free before any attempt. (2) A voice attempt is claimed before scoring and refunded on a match; before, guesses fired together were all scored but only one counted, multiplying the guess budget. React review: a double-tap on Record opened a second recording and left the first microphone stream on (now guarded by refs, not state); expiry, Cancel, or Escape while recording now stop the microphone; a declined card's error takes focus so it is not raced by the heading. Scores now show three decimals and "just below your threshold" for near misses (a 0.6179 against 0.618 had displayed as a tie).
- **Why:** Review gate for Phase 4, and a confusing display seen in the first live test.
- **Verify:** `make test` (73 passed), including `test_switching_cards_is_refused_even_before_any_attempt` and `test_simultaneous_guesses_each_use_an_attempt` (a second guess fired while the first is scored now uses its own attempt).
- **Risk/Notes:** First live results for the enrolled demo user (8 takes): latency 0.49 to 0.58 s, well under the 2 s target; no false replay flags; "ahh" passed 3 of 3, "banana" 0 of 2 (one by less than 0.001), "hum" 0 of 3 (0.39 to 0.51 against 0.619). Checked and ruled out: scoring determinism (re-embedding stored audio reproduces stored embeddings exactly), template math (centroids and thresholds match the formula), and the browser resampler change made after enrollment (it moves a score by under 0.01). The cause is enrollment capturing a single moment: each sound's five takes were recorded back to back in about 15 seconds, so the template and its spread reflect within-moment variation only. Options are with the user.

---

### 2026-09-25 20:56 - Phase 4: voice challenge at checkout

- **Files:** issuer/liveness.py (new), issuer/approvals.py, issuer/verification.py, web/src/issuer/{ApprovalWidget.jsx,issuerApi.js}, web/src/styles.css, tests/test_boundary.py, tests/test_challenge.py (new)
- **What:** The stub `POST /v1/sessions/{id}/verify` is replaced by `identify` (binds the card, returns two of the person's sounds in random order, or the passkey), `voice` (both takes scored against their own sound's template and personal threshold, plus replay detection by normalized cross-correlation against stored enrollment audio; each take logged to `verifications` with score, threshold, replay flag, and latency), and `passkey` (STUB until Phase 6). Two failed attempts, fewer than three confident sounds (§7.2), or an amount at or above `STEP_UP_AMOUNT` lead to the passkey; a step-up voice pass is recorded as `method='voice'` while the session stays pending. The bank widget now runs the whole flow: choose card, record each requested sound (tap to start, tap to stop), see the scores and threshold (bank side only), retry with a fresh pair, or use the passkey.
- **Why:** Plan Phase 4: approval by voice, per docs/ALGORITHM.md §7.5 and §7.6.
- **Verify:** `make test` (72 passed; 11 new in tests/test_challenge.py covering a match, retry then passkey fallback, replay, a too-short take not costing an attempt, step-up, low-confidence routing, and refusing a card switch after an attempt). Live: a checkout for the enrolled demo user returns `{"mode":"voice","challenge":[...2 sounds...],"attempts_left":2}`.
- **Risk/Notes:**
  - Rebuilt after the branch was reverted to 8ddff01 (commit f8dc49c), which discarded an earlier uncommitted Phase 4 attempt. This version includes that attempt's self-review fixes from the start: re-identifying keeps the issued challenge (no re-rolling), switching cards after an attempt is refused (no resetting the count), and a released payment claim keeps the cardholder and any voice pass.
  - STUB: `POST /v1/sessions/{id}/passkey` completes without a WebAuthn assertion, but only where the real flow asks for a passkey. Phase 6 replaces it.
  - Replay detection catches the same file replayed, not audio played through a speaker into a microphone; the randomized challenge and the step-up passkey cover that. The test data needed a small per-take pitch variation for this reason: two takes of a pure tone correlate at 0.998 and are correctly flagged as a replay.
  - Scores and thresholds appear only in the bank widget. The merchant response is unchanged: exactly `{verified, transaction_id}`.
  - Not yet measured: the under-2-second latency with real voice. `latency_ms` is logged per attempt for that.

---

### 2026-09-25 17:40 - Personal threshold uses held-out spread (ADR 3)

- **Files:** issuer/verification.py, issuer/enrollment.py, tests/test_verification.py, docs/ALGORITHM.md (§7.2 step 4), docs/DECISIONS.md (ADR 3)
- **What:** `spread()` is now the leave-one-out mean (each sample against the centroid of the others). `in_sample_spread()` keeps the original formula for the Phase 8 comparison only. The existing dev templates were recomputed from their stored samples.
- **Why:** The in-sample formula overstated a fresh take's score by about 0.10 on real data, so only 11 of 15 genuine held-out takes passed, and the overstatement grows with variability, penalizing the people the personal threshold is for. Decided with the user (option B).
- **Verify:** `make test` (61 passed), including exact-value tests for both formulas and a test that the bias grows with variability.
- **Risk/Notes:** This changes a §7 definition, so ADR 3 is required and was added. Thresholds are lower (0.60 to 0.62 for the enrolled demo user, from 0.70 to 0.72), which may raise false accepts; Phase 8 must report both formulas on TORGO. Restart the issuer (no auto-reload) to load it.

---

### 2026-09-25 17:30 - Issuer runs without auto-reload

- **Files:** Makefile, docs/CONTEXT.md (§12)
- **What:** `make issuer` no longer passes `--reload`. The merchant (`make api`) still reloads.
- **Why:** On Windows the reloader hung mid-restart on the issuer after edits (it loads the speaker model at import) and kept serving the old code with no visible sign, which is worse than no reload during a demo. Decided with the user.
- **Verify:** `make -n issuer` prints no `--reload`; the issuer log has no "Will watch for changes" line; `curl localhost:8100/healthz` returns `{"status":"ok","encoder":"resident"}`.
- **Risk/Notes:** After any edit under `issuer/` or `ml/`, restart the issuer by hand. The user's first live-microphone enrollment succeeded (3 sounds, 15 takes of 1.9 to 3.1 s, cohesion 0.60 to 0.63, no re-records), which closes the open verification item from the Phase 3 entry.

---

### 2026-09-25 17:18 - Phase 3: speaker encoder and voice enrollment

- **Files:** ml/encoder.py, ml/constants.py, issuer/{verification.py,enrollment.py,config.py,db.py,main.py}, web/src/issuer/{recorder.js,EnrollPage.jsx,issuerApi.js}, web/src/{App.jsx,styles.css}, web/src/lib/router.js, tests/{test_verification.py,test_health.py,test_guards.py}
- **What:** `ml/encoder.py` loads ECAPA once at import from `models/ecapa` (no download, no symlinks), warms it with one inference, asserts 16 kHz mono (raises `AudioFormatError`, never resamples), peak-normalizes, and returns an L2-normalized 192-dim float32. Issuer `/healthz` now reports `"encoder": "resident"`. `issuer/verification.py` implements §7.2 and §7.3: `decode_upload`, `check_recording` (too short, too long, too quiet, each with an actionable message), `cohesion`, `centroid`, `spread`, `personal_threshold`. New router `issuer/enrollment.py`: progress, per-take upload (multipart WAV), finalize, and start over. Low cohesion gets one guided re-record and is then accepted as `low_confidence` and logged, so enrollment never dead-ends (§2.4). New table `enroll_labels` tracks re-records. Bank-styled enrollment screen at `#/bank/enroll` (demo sign-in stub, then name a sound and record it 5 times). Capture turns browser echo cancellation, noise suppression, and auto gain off, and converts to 16 kHz mono PCM16 WAV in the browser with an `OfflineAudioContext`.
- **Why:** Plan Phase 3: the voiceprint that Phase 4 verification compares against.
- **Verify:** `make test` (59 passed). `curl localhost:8100/healthz` returns `{"status":"ok","encoder":"resident"}`. Measured: model load 1.4 s, embedding of 2 s of audio about 130 ms on CPU. In the browser, a 1.6 s 44.1 kHz stereo WAV converts to exactly 25,600 samples at 16 kHz and the issuer accepts it; a too-quick tap-tap shows the "hold it longer" advice, releases the microphone, and uploads nothing.
- **Risk/Notes:**
  - **Live microphone capture is not yet verified.** Headless Chromium cannot run a real-time capture stream, so only the conversion and upload path was proven automatically. A human test at `#/bank/enroll/maya` is pending.
  - Review gate: Python reviewer (read-modify-write race in `finalize` could exceed the re-record limit, a concurrent start-over could leave a hidden template, the upload size check is not a DoS guard) and React reviewer (microphone left on when setup fails after permission; unhelpful message for a very short take; no warning before the 10 s auto-stop; label read from the render closure; uploads not aborted on navigation). All fixed except the last, deliberately: an upload that completes after navigation still saves a valid take, which the person sees on return.
  - Also fixed while testing: decoding used a hardware `AudioContext` whose `close()` could hang with no audio output and leave the UI on "Saving…"; decoding now uses an `OfflineAudioContext`, which also resamples to 16 kHz directly. The Stop button no longer changes its own label every 100 ms (screen readers would re-announce it); the timer is a separate visual element.
  - STUB: enrollment has no authentication; in a real deployment it sits behind the bank's own login.
  - Schema: new table `enroll_labels` (created automatically; no reset needed). Tests use synthetic tones only, never speech (§2.3).
  - uvicorn `--reload` hung on the issuer again after an edit (see docs/CONTEXT.md §12); restarted by hand.

---

### 2026-09-25 16:55 - Phase 2: Seaside Market storefront and the bank widget

- **Files:** web/src/{App.jsx,main.jsx,styles.css}, web/src/lib/{api.js,cart.jsx,announce.jsx,router.js,money.js}, web/src/components/{SiteHeader,CartDrawer,PageHeading,Icons}.jsx, web/src/pages/{Shop,Checkout,Receipt}.jsx, web/src/issuer/{ApprovalWidget.jsx,issuerApi.js,icons.jsx}, web/public/products/*.jpg (18), web/package.json, web/package-lock.json, scripts/{seed_demo.py,seed_catalog.json}, api/checkout.py, issuer/{approvals.py,config.py,db.py}, tests/{test_boundary.py,test_guards.py}, design-system/seaside-market/MASTER.md, docs/CONTEXT.md (§12), README.md, .gitignore
- **What:** Accessible storefront built with the ui-ux-pro-max skill (design system persisted to `design-system/seaside-market/MASTER.md`, with a "Timbre overrides" section where the generated values failed contrast or did not fit a test harness). Shop grid in four sections, native-`<dialog>` cart drawer, checkout priced by the server, receipt that shows the complete approval the store received. The bank's widget (`web/src/issuer/`) has its own navy identity and its own icons, imports nothing from the storefront, and tells the store only that it closed. 18 real products from Open Food Facts with local photos (two candidates rejected because their photos showed people's bodies and homes); prices are approximate, set by hand. `make seed` loads the catalog and two fictional cardholders whose cards are tokenized from Stripe's named test tokens, never a card number. New merchant endpoints `POST /cart/quote` and `GET /orders/{id}`. New issuer endpoint `POST /v1/sessions/{id}/extend`; `GET /v1/sessions/{id}` now returns `seconds_remaining` and `extensions_left`.
- **Why:** Plan Phase 2: a platform to test the verification layer on, built to the §13.1 accessibility floor.
- **Verify:** `make test` (39 passed). `make reset && make dev`, then at http://localhost:5173: add items, open the cart, check out, approve in the bank widget, land on the receipt. Verified in headless Chromium: full purchase; Escape-cancel then retry; keyboard path from the skip link; focus after every navigation, removal, and widget phase; 60-second expiry warning and "I need more time"; 375px with no horizontal scroll and every button at least 44px; no console errors. The network log after approval shows one merchant call, `POST /checkout/complete`, returning 78 bytes.
- **Risk/Notes:**
  - Review gate: React reviewer (race: Cancel or Escape during "Approving" could let the store finalize before the bank answered and risk a double charge; cart drawer dead-ended when the catalog had not loaded; overlapping catalog fetches) and accessibility reviewer (focus hidden under the sticky header, WCAG 2.4.11; no warning or extension before the 5-minute bank session expired, WCAG 2.2.1; duplicate announcement from `<output>`; focus jumping to the top after each removal; focus churn on the "submitting" phase; a button inside `role="alert"`). All nine fixed. The Cancel-during-request guard is verified by reading the code only: the fake provider answers too fast to press Cancel mid-request.
  - Schema change: `sessions.extensions` added. Run `make reset`.
  - `tests/test_guards.py` now enforces the browser half of ADR 2 (the issuer folder imports only React and itself; the storefront may only mount `ApprovalWidget`) and exempts card-number-like digit runs that start with 0, since card numbers never do and product barcodes often do; one real barcode passed Luhn by chance.
  - New dependencies: `@fontsource-variable/rubik` and `@fontsource-variable/nunito-sans`, so fonts are bundled locally instead of loaded from Google Fonts on venue wifi.
  - `.gstack/` added to `.gitignore` by the gstack browse tool (its local state).
  - Deliberate UI choices: product photos use `alt=""` because brand and name are the adjacent text; recording will be tap-to-start/tap-to-stop, never hold-to-talk.

---

### 2026-09-25 16:20 - Phase 1 review fixes (security and Python reviewers)

- **Files:** issuer/approvals.py, issuer/db.py, tests/test_boundary.py, tests/test_guards.py
- **What:** (1) `verify` no longer holds the SQLite write lock across the payment call: a short transaction claims the session (`pending` to new state `processing`), the provider runs with no lock held, and a second short transaction settles it. This supersedes the lock note in the 16:05 entry. (2) Any payment failure (decline, capture failure, or provider exception) returns the session to `pending` instead of the terminal `failed`, so the shopper can retry; `verify` answers `{"status": "payment_failed"}`, and exceptions still propagate. A session stuck in `processing` expires like a pending one. (3) `GET /v1/cardholders` became `GET /v1/sessions/{id}/cardholders` and requires a live pending session, so the demo cardholder list cannot be browsed outside a checkout. (4) New guard test: no import of a concrete provider outside `issuer/payments/`.
- **Why:** Reviewer findings: the lock would stall every other issuer write behind Stripe latency and surface as a raw 500; a failed capture dead-ended the purchase (non-negotiable §2.4); the cardholder list was reachable without any session.
- **Verify:** `make test` (34 passed). New tests: `test_cardholder_list_requires_a_live_session`, `test_payment_failure_never_dead_ends_the_session` (decline and capture failure, then a successful retry), `test_provider_exception_releases_the_session`, `test_concrete_providers_stay_inside_payments_package` (regex checked against 7 positive and negative cases).
- **Risk/Notes:** Schema change: `sessions.status` now allows `processing`; recreate dev databases with `python -m scripts.reset_db`. Status `failed` is currently unused; it is kept for Phase 4/6 to mark a session the shopper abandons. Test payment doubles subclass the `PaymentProvider` interface, not `FakeProvider`.

---

### 2026-09-25 16:05 - Phase 1: merchant/issuer boundary with stub approval

- **Files:** issuer/approvals.py, issuer/payments/{__init__,base,fake_provider}.py, issuer/main.py, issuer/config.py, issuer/db.py, api/checkout.py, api/cart.py, api/catalog.py, api/issuer_client.py, api/config.py, api/main.py, api/db.py, tests/test_boundary.py, docs/DECISIONS.md (ADR 2), CLAUDE.md (§1.1 snippet)
- **What:** Merchant: `GET /catalog`; `POST /checkout/confirm` prices the cart from the catalog (integer cents, flat demo tax and shipping as named constants), originates `instruction_id`, opens an issuer session, records a pending order; `POST /checkout/complete` returns exactly `{verified, transaction_id}`. `api/issuer_client.py` is the merchant's only channel to the issuer and refuses any approval response with extra keys. Issuer: `POST /v1/sessions`, `POST /v1/approve` (response model with exactly two fields), and widget endpoints `GET /v1/cardholders`, `GET /v1/sessions/{id}`, `POST /v1/sessions/{id}/verify`. `PaymentProvider` ABC exactly as §9.3, chosen by `get_provider()`.
- **Why:** Plan Phase 1: the privacy boundary exists and is tested before any ML or UI depends on it.
- **Verify:** `make test` (29 passed). Live, across real processes: confirm, then complete (`{"verified":false,"transaction_id":null}`), then widget verify, then complete (`{"verified":true,"transaction_id":"fake_txn_..."}`), with body and headers checked by curl.
- **Risk/Notes:**
  - Architecture change, see ADR 2: issuer-hosted challenge, and the merchant sends no cardholder identity. Schema changes that follow from it: `orders.user_id` removed; `sessions.user_id` nullable until the widget binds it. Existing dev databases must be recreated (`python -m scripts.reset_db`).
  - STUBS, logged so they do not ship: `FakeProvider` (approves everything, moves no money; `get_provider()` prints `STUB: ... using FakeProvider` on every issuer start and refuses to run it once `STRIPE_SECRET_KEY` is set). `POST /v1/sessions/{id}/verify` approves any seeded cardholder with no verification; replaced in Phase 4 (voice) and Phase 6 (passkey).
  - `tests/test_boundary.py` checks body keys and every response header (allowlist with fixed values; `vary: Origin` from the CORS middleware is the only extra). Negative controls confirmed it fails on an extra header, a modified `vary`, and an issuer response with an extra `score` key.
  - The verify path holds the SQLite write lock across the provider call so two concurrent verifies cannot both charge. Fine at demo scale; revisit if Stripe latency causes lock waits.
  - If capture fails after a successful authorization, the error is logged and the authorization is left open. `TODO(Phase 5)`: void it once Stripe can fail there.
  - `httpx` is now a runtime dependency of the merchant (server-to-server calls), not only a test dependency. Chosen over `requests` because FastAPI's TestClient is an httpx client, so tests run the real merchant code path against the issuer in-process.

---

### 2026-09-25 15:54 - Phase 0: environment and three-service scaffold

- **Files:** requirements.txt, Makefile, .gitignore, pytest.ini, CLAUDE.md (§4.2, §6), api/{__init__,config,db,main}.py, issuer/{__init__,config,db,main}.py, ml/{__init__,constants}.py, scripts/{__init__,warm_cache,reset_db}.py, tests/{conftest,test_health,test_guards}.py, web/{package.json,package-lock.json,vite.config.js,index.html}, web/src/{main.jsx,App.jsx,styles.css,lib/api.js,issuer/issuerApi.js}
- **What:** Python 3.12 venv with every requirement pinned to the exact version that was installed and smoke-tested (torch/torchaudio held at 2.5.1 because later torchaudio removed the backend API SpeechBrain relies on). Merchant (:8000) and issuer (:8100) FastAPI apps, each with `/healthz`, CORS limited to the web origin, and a raw-SQL SQLite layer (one connection per operation, WAL, `BEGIN IMMEDIATE` writes) that creates its schema on startup. The issuer schema has no PAN column; `payment_tokens` holds a provider token and last four only. `issuer/config.py` holds every §7 constant by name with the ALGORITHM.md values. Vite 8 plus React 19 app written by hand (no `npm create`, which prompts interactively); it refuses to start if `WEBAUTHN_ORIGIN` does not match its own origin, and serves on `localhost` with `strictPort`. ECAPA (models/ecapa) and TORGO (data/torgo_hf, 1565 MB, 4 parquet shards) downloaded by `scripts/warm_cache.py`.
- **Why:** Plan Phase 0: every later phase plugs into this skeleton.
- **Verify:** `make test` (11 passed). `make dev`, then `curl localhost:8000/healthz` and `curl localhost:8100/healthz` both return `{"status":"ok"}`, and http://localhost:5173 shows Merchant: online, Issuer: online (confirmed in headless Edge).
- **Risk/Notes:**
  - Deviations from the spec: Python 3.12, not 3.11 (the only interpreter installed; all dependencies support it). Makefile rewritten to call the venv interpreter directly, read ports from `.env`, pass `--env-file .env` to uvicorn, and limit `--reload` to the service's own directories so it does not watch the 1.5 GB corpus. `make reset` now calls `scripts/reset_db.py` instead of `rm -f` so it works without a POSIX shell (tested from Git Bash, PowerShell, and cmd). It also removes the `-wal`/`-shm` files, which `.gitignore` now covers.
  - New dependencies: `httpx` (required by FastAPI's TestClient; nothing in the stack provides it) and `huggingface_hub` (previously only transitive via speechbrain/datasets; `warm_cache.py` uses it directly, so it is now pinned). Web: `@simplewebauthn/browser` (the §6 passkey library), `vite`, `@vitejs/plugin-react`, `react`, `react-dom`, all pinned exactly.
  - Files not in the §5.2 layout: `api/config.py` (the merchant cannot import `issuer/config.py`, so it needs its own), `ml/constants.py` (model/corpus paths without loading the model, which `ml/encoder.py` does at import), `scripts/reset_db.py`, `tests/test_health.py`, `tests/test_guards.py`, `web/src/issuer/issuerApi.js` (browser half of the issuer-hosted challenge; ADR #2 lands with Phase 1).
  - `tests/test_guards.py` enforces §2.1 (no ASR import under issuer/, checked both directly and transitively in a fresh interpreter; a negative control confirmed it catches one) and §2.2 (no Luhn-valid 13 to 19 digit number anywhere in source).
  - CLAUDE.md §4.2 was missing `npm --prefix web install`; added.
  - `/healthz` on the issuer does not yet confirm the model is resident; that arrives with `ml/encoder.py` in Phase 3.
  - `make seed` and `make eval` fail until `scripts/seed_demo.py` (Phase 2) and `scripts/run_eval.py` (Phase 8) exist.

---

### 2026-09-25 19:55 - Reverted to Claude-only instruction file

- **Files:** CLAUDE.md (now the full guide), AGENTS.md (deleted)
- **What:** Merged AGENTS.md back into CLAUDE.md and removed the import stub. §13 retitled to "Conventions for Claude". Added a portability note in the header describing the exact steps to switch to AGENTS.md later. Companion docs in `docs/` are unchanged and still loaded via the trigger table.
- **Why:** The project is Claude Code only for now. One file is simpler than a file plus an import stub, and the split added a failure mode for no current benefit.
- **Verify:** `ls` shows CLAUDE.md and no AGENTS.md; open Claude Code and ask it to state non-negotiable §2.5 without pasting anything.
- **Risk/Notes:** Codex and Cursor will not see this file. If anyone on the team uses them, follow the portability note in the CLAUDE.md header.

---

### 2026-09-25 19:45 - Added repository scaffolding

- **Files:** .gitignore, .env.example, Makefile, requirements.txt, README.md, docs/DECISIONS.md, docs/DEMO.md
- **What:** Created the files AGENTS.md §4.3 and §4.4 specify. .env.example matches the §4.3 variable list exactly. Makefile implements every §4.4 target. DECISIONS.md carries an ADR template plus the empty Visa Intelligent Commerce mapping table that §9.2 requires for the Devpost. DEMO.md is the runner's short form of §16.
- **Why:** The instruction set referenced these files as if they existed. An agent told to run `make seed` against a missing Makefile wastes a turn inventing one.
- **Verify:** `make test` runs pytest (currently no tests, exits clean); `cat .env.example` matches AGENTS.md §4.3 line for line.
- **Risk/Notes:** No source code yet. `make dev` will fail until `api/main.py`, `issuer/main.py`, and `web/` exist. requirements.txt is unpinned; pin versions once the build is working so a reinstall at hour 30 cannot break it.

---

### 2026-09-25 19:20 - Split single CLAUDE.md into AGENTS.md plus docs

- **Files:** AGENTS.md (new), CLAUDE.md (now a one-line import), docs/ALGORITHM.md (new), docs/CONTEXT.md (new), docs/CHANGELOG.md (new)
- **What:** The 40 KB single-file guide became AGENTS.md (about 20 KB, operational core) plus three companion docs. CLAUDE.md now contains only `@AGENTS.md`. Section numbers were preserved across the split, so cross-references such as "non-negotiable §2.5" still resolve. Renamed §13 from "Conventions for Claude" to "Conventions for coding agents".
- **Why:** Codex reads AGENTS.md and does not read CLAUDE.md. Claude Code reads AGENTS.md only when CLAUDE.md is absent, so the import line keeps one source of truth for both. The original file also risked silent truncation by Codex CLI past project_doc_max_bytes.
- **Verify:** `wc -c AGENTS.md` is under 24 KB; `cat CLAUDE.md` prints `@AGENTS.md`; open a session in each agent and ask it to state non-negotiable §2.5 without being given the file.
- **Risk/Notes:** Companion docs are only read if the agent follows the trigger table at the top of AGENTS.md. If an agent skips them, move the triggering rule inline. Claude Code needs v2.1.277 or later for AGENTS.md support, and that support is unavailable on Bedrock, Vertex, or with telemetry disabled; the CLAUDE.md import line covers those cases regardless.

---

### 2026-09-25 18:40 - Full proofread; ambiguities made explicit

- **Files:** CLAUDE.md
- **What:** Fixed misspelled model id (`spkrec-ecapa-veoxceleb` to
  `spkrec-ecapa-voxceleb`). Resolved a contradiction where `PaymentProvider`
  lived in `api/` (merchant) while tokens were said to live with the issuer:
  payments now live in `issuer/payments/` and the merchant never receives a
  token reference, so the merchant response is `{verified, transaction_id}`
  everywhere. Defined `instruction_id` ownership. Defined the 2-second latency
  measurement. Stated enrollment is 3 labels times 5 recordings. Added an
  explicit non-hard-fail path for low-cohesion enrollment so §2.4 is not
  violated. Added §4.3 environment variables, §4.4 Makefile targets, §5.1
  ownership, §13.4 testing, §17 glossary, and a table of contents. Added the
  WebAuthn cross-origin gotcha. Named `INTENT_CONFIDENCE_MIN` and
  `MAX_VOICE_ATTEMPTS`. Removed em dashes throughout and added a style rule.
- **Why:** The document implied several things it never stated, and one
  contradiction (token ownership) would have produced an architecture that
  breaks the privacy argument the project is built on.
- **Verify:** n/a (documentation)
- **Risk/Notes:** The issuer-holds-all-tokens model is stricter than real
  network tokenization, where merchants do receive tokens. That is deliberate,
  for demonstrability. If a judge challenges it, say so plainly.

---

### 2026-09-25 17:15 - Added product model (§1.1)

- **Files:** CLAUDE.md
- **What:** New §1.1 stating Timbre is issuer-side infrastructure and the
  storefront is a test harness. Added two answers to §16.
- **Why:** The architecture implied this but never said it, risking effort sunk
  into storefront features and a weak answer to "is this a product or a
  protocol?"
- **Verify:** n/a (documentation)
- **Risk/Notes:** Rules out browser-extension and real-merchant-integration
  approaches. If that constraint is ever revisited, log it here.

---

### 2026-09-25 16:00 - Repository initialized

- **Files:** CLAUDE.md
- **What:** Project guide created. No code yet.
- **Why:** Establish scope, constraints, and working agreement before build.
- **Verify:** n/a
- **Risk/Notes:** All §4.1 pre-event tasks outstanding. Visa access unresolved.

---
