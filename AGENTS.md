# AGENTS.md - Timbre

## Handoff (read first; updated 2026-09-25, moved from Claude Code to Codex)

**First action:** read this file, then `docs/CHANGELOG.md` (newest first), `docs/DECISIONS.md` (ADR 1-4), and `docs/CONTEXT.md` §12. Read `docs/ALGORITHM.md` before touching `issuer/`, `ml/`, or payments. Then give the person running Codex a short summary: what is done, what is next, open decisions.

**Done (Phases 0-6, 96 tests pass via `make test` as of Phase 8):** three services (merchant :8000, issuer :8100, Vite web :5173); privacy boundary (merchant learns only `{verified, transaction_id}`, enforced by tests); accessible storefront + bank widget; ECAPA enrollment, interleaved (ADR 4), held-out spread thresholds (ADR 3); voice challenge 2-of-3 with replay check and 2-attempt fallback; real WebAuthn passkeys; Stripe test-mode payments. Stubs remaining: enrollment/passkey registration have no auth (demo sign-in); `visa_provider` not built.

**Also done since the Codex handoff (109 tests):** Phase 8 run (`make eval`; ADR 3: EER 6.7% control, 8.8% dysarthric). Phase 7 code (merchant n-best ASR, LLM rerank, keyword fallback, confirm-before-add UI), checked against real Whisper. Baseline page (`#/baseline`, `make baseline`). Phase 9 adaptation in the live voice path plus Dashboard drift chart (`#/dashboard`, `make drift`). Numbers are in the 2026-09-26 00:40 CHANGELOG entry. Each demo machine needs `scripts.warm_asr`, then `make eval && make baseline && make drift` once (outputs are gitignored).

**Next, in order:**
1. Phase 7 live: set `LLM_API_KEY` and try a spoken item end to end. The rerank on-vs-off intent-accuracy delta (§3.2) needs real recordings of people naming catalog items; TORGO has none and §2.3 forbids imitating them.
2. Decide whether adaptation needs a cumulative drift cap: per-update `MAX_DRIFT` holds, but templates drifted 0.18 to 0.32 over many updates in `make drift` (impostor accept 1.46% -> 1.96%).
3. Spoken confirmation (§10.3) and dispute drafting (§10.4) are not built.
3a. Accuracy: cheap candidates rejected (ADR 7); encoders not adopted (ADR 8); fusion failed a pre-registered test on EasyCall (ADR 9), while the live design held (dysarthric EER 2.43%, 2.84% vs same-word attackers). Quote only with ADR 9's caveats.
4. Phase 10: demo hardening, `docs/DEMO.md`, VIC mapping in ADR 1, README/Devpost (check `docs/CONTEXT.md` §11 before claiming anything).

**Open decisions for the person:** (a) purchases >= $50 fall back to passkey-only after 2 failed voice attempts (recommended keep, record as ADR 5); (b) roll the Stripe test key after the event (it was shared in chat).

**Unverified by a human:** a real Windows Hello passkey prompt; a full UI purchase through Stripe.

**Environment (Windows):** Python 3.12 venv, call `.venv/Scripts/python.exe` directly; GNU make via winget (new shells have it on PATH); the issuer runs without `--reload` (restart it after any `issuer/` or `ml/` edit); `make reset` wipes voice enrollments and passkeys, `make seed` is safe to rerun; `.env` holds the Stripe test key (gitignored); push to remote `private` (default upstream).

**Working rules kept from Claude Code:** every edit gets a `docs/CHANGELOG.md` entry; review impactful edits; no em dashes; the §2 non-negotiables are absolute.

> Working agreement for coding agents (Codex, Claude Code) on this repository.
> Read this file top to bottom before your first action in a new session.
>
> Portability note: if this project is ever opened in Codex, Cursor, or Gemini
> CLI, rename this file to `AGENTS.md` and replace `CLAUDE.md` with the single
> line `@AGENTS.md`. Those tools read AGENTS.md and ignore CLAUDE.md. Log the
> change in `docs/CHANGELOG.md`.
>
> **Every edit gets an entry in `docs/CHANGELOG.md`.** No exceptions.
>
> Style rule for anything you write in this repo (docs, README, Devpost text):
> do not use em dashes. Use commas, colons, parentheses, or separate sentences.

## Companion files: read these when the trigger applies

| File | Read it before |
|---|---|
| `docs/ALGORITHM.md` | Touching `issuer/verification.py`, `issuer/liveness.py`, `ml/`, `issuer/payments/`, or `api/llm.py`. Contains the verification algorithm with every tunable constant, the TORGO data rules, the payments interface, and the required generative-AI usage. |
| `docs/CONTEXT.md` | Writing any README, pitch, or Devpost text (prior art; do not overclaim). Also when debugging something mysterious (known issues table), and when preparing the demo. Contains the glossary. |
| `docs/CHANGELOG.md` | Every edit, without exception. Append there, newest first. |

These are not optional background reading. The triggers above are instructions.

---

## 1. What this project is

**Timbre** is a payment-approval system that verifies *who is speaking* from the
acoustic properties of a person's voice, instead of verifying *what they said*.

The user it exists for: adults with dysarthria (a motor speech disorder) caused
by stroke, Parkinson's disease, cerebral palsy, multiple sclerosis, or ALS.
Roughly 2.7 to 4 million adults in the US. These people understand language
perfectly and think clearly; their articulation is impaired. Every voice-gated
system in finance (IVR menus, voice biometric enrollment, "say your card
number") requires intelligible articulation, so it rejects them. The real-world
fallback is asking a family member to call the bank on their behalf, which means
handing over card numbers and account access. That is the harm we are addressing.

The insight the whole project rests on:

> Identity lives in the acoustics (vocal tract shape, pitch, resonance).
> Intelligibility lives in articulation. Current systems conflate the two and
> reject people for failing a test that was never necessary.

Built for **HackGT 13** (Georgia Tech, September 25 to 27, 2026), targeting the
**Visa challenge: Reimagine Shopping with Generative AI** ($5,000 first place)
and a disability or social-impact track.

### 1.1 Product model: read this before building any UI

**Timbre is infrastructure, not a consumer app.** The deliverable is the
verification layer that lives with the issuer. The closest analogy is 3-D
Secure: the cardholder never installs anything, their bank enables it, and
merchants inherit it.

**The storefront in `web/` and `api/` is a test harness, not the product.** It
exists to prove two things: that a merchant can consume this in a few lines of
code, and that the merchant learns nothing about the user. Do not invest effort
in it beyond what the demo requires. No product search or filtering, no reviews,
no user accounts, no merchandising, no order history.

Consequences for how we build:

- **We do not integrate into a real shopping site.** No browser extension, no
  DOM scraping, no driving someone else's checkout with Playwright or similar.
  That path breaks on every redesign and would require touching live card
  fields, violating non-negotiable §2.2.
- **The merchant/issuer boundary is the demo.** Anything that blurs it to save
  time deletes the argument we are making.
- **Keep the merchant-side integration to a snippet we can show on screen.**
  The merchant opens a session, hands the shopper to the issuer's challenge
  (as 3-D Secure does), then collects a completed authorization. It never
  touches audio and never says who the shopper is (docs/DECISIONS.md ADR 2):

  ```python
  # merchant side, in full (server to server; real code: api/issuer_client.py)
  issuer = httpx.Client(base_url="http://127.0.0.1:8100")
  session_id = issuer.post("/v1/sessions", json={
      "instruction_id": instruction_id, "amount_cents": total, "merchant_id": MERCHANT_ID,
  }).json()["session_id"]
  # ...browser hands session_id to the issuer widget; the shopper verifies there...
  approval = issuer.post("/v1/approve", json={"instruction_id": instruction_id}).json()
  # approval == {"verified": True, "transaction_id": "..."}  and nothing else
  ```

- **Use real product data.** About 20 real items with real names, prices, and
  images. "Product A, $9.99" makes the harness look like a mock and undercuts
  the pitch. Given the HackGT 13 theme is Seaside Market, a market or grocery
  catalog is a reasonable choice, but any real catalog is fine.

If asked "is this a product or a protocol?", the answer is protocol. The only
consumer-facing surface in a real deployment is enrollment, which would live
inside the bank's existing app. A standalone Timbre app is the weakest version
of this idea, because it would have no relationship with anyone's card.

---

## 2. Non-negotiables

These are not preferences. Violating any of them invalidates the project.

1. **Never transcribe audio in the identity path.** ASR is used only to
   determine what the user wants to buy. No import of `faster_whisper`, no call
   to any ASR model, anywhere under `issuer/`. That conflation is the exact
   failure mode we exist to fix.
2. **Never store a PAN (primary account number, i.e. a card number).** No
   database column, no variable that outlives a single function call, no log
   line, no `.env` entry, no test fixture. Token references and last-four digits
   only. The schema is shown on screen during judging as evidence.
3. **Never simulate disabled speech.** No teammate doing an impression, in the
   evaluation data, in the demo, or in a test fixture. Use corpus recordings
   only. If we lack data for a claim, we state that we lack it.
4. **Never dead-end the user.** Every failure path terminates in a usable
   alternative (the WebAuthn passkey in §7.6), never in "call this number" or
   "have someone else verify for you." This applies to enrollment failures too,
   not just verification failures.
5. **Never leak accessibility status to the merchant.** The merchant-facing
   response body contains exactly `{verified, transaction_id}` and nothing else.
   No score, no threshold, no method used, no number of attempts, no accessibility
   profile, no HTTP header carrying any of it.
6. **Never claim novelty we do not have.** Dysarthric speaker verification
   exists in academic literature (§11). We are building a deployment, not
   inventing an algorithm. Any README, pitch, Devpost text, or code comment you
   write must reflect that.

---

## 3. End goal (definition of done)

### 3.1 MVP: must exist by hour 30, or we have nothing

- [ ] A user can enroll **3 distinct sound labels**, with **5 recordings each**
      (15 recordings total), in the web UI. Sound labels are the user's choice:
      a word, a hum, a sustained vowel, any repeatable vocalization.
- [ ] A user can shop by voice and reach a checkout with a real cart total.
- [ ] The approval step verifies the speaker acoustically and returns a result.
      **Latency target: under 2 seconds**, measured from the moment the client
      finishes uploading audio to the moment the client receives the response.
      Model load time is excluded because the model is warmed at boot (§12).
- [ ] A payment is executed against a sandbox (Stripe test mode by default, see
      §9) and a receipt renders in the UI.
- [ ] Two consecutive failed verifications fall back to a WebAuthn passkey, and
      that passkey path completes a real purchase.
- [ ] The merchant-side network payload visibly contains only
      `{verified, transaction_id}`, viewable in browser devtools.
- [ ] Baseline comparison screen: transcription-based verification run on the
      same dysarthric audio, failing, side by side with Timbre succeeding.

### 3.2 Should have

- [ ] Offline evaluation on TORGO: EER reported separately for control speakers
      and dysarthric speakers.
- [ ] Template adaptation with a drift chart across simulated time.
- [ ] LLM n-best reranking with a measured intent-accuracy delta (on vs off).
- [ ] Anti-replay: randomized 2-of-3 challenge plus near-duplicate rejection.

### 3.3 Nice to have (cut these first, in this order)

- [ ] Post-purchase dispute drafting.
- [ ] Amount-tiered step-up wired to Visa Transaction Controls rather than local
      logic.
- [ ] Mobile-responsive layout.
- [ ] Multi-item carts, loyalty, returns.

### 3.4 Explicitly out of scope

Do not build any of these, even if there is spare time:

Production security hardening. Any handling of real cardholder data. Multiple
languages. Native mobile apps. Any clinical or diagnostic claim about a user's
condition. Account recovery or password reset flows. User registration beyond
the seeded demo users. Deployment to a public host. Rate limiting. Admin panels.

---

## 4. Starting point, environment, commands

Assume an empty repository unless the working tree says otherwise. Do not assume
any file in §5.1 exists; check first.

### 4.1 Pre-event checklist (complete before Friday September 25)

| Task | Owner | Status | Notes |
|---|---|---|---|
| Visa Developer account and sandbox project | | ☐ | https://developer.visa.com/identity/user/register |
| Two-way SSL working, one successful sandbox call | | ☐ | Test in VDC Playground before writing client code |
| Visa Intelligent Commerce access request submitted | | ☐ | Gated product; assume no response in time (§9.1) |
| TORGO cached locally (primary) | | ☐ | `abnerh/TORGO-database` on HuggingFace |
| TORGO cached locally (backup) | | ☐ | `pranaykoppula/torgo-audio` on Kaggle |
| SpeechBrain ECAPA model cached | | ☐ | About 80 MB. Do not download on venue wifi. |
| Stripe test keys | | ☐ | The realistic payments path |
| LLM API key (Anthropic or Gemini) | | ☐ | |
| Headset microphone acquired | | ☐ | Laptop mics fail in the expo hall |
| Contact attempted with Georgia Tech CIDI | | ☐ | One conversation with a real user beats any feature |

### 4.2 First commands in a fresh clone

```bash
python3.12 -m venv .venv        # Windows: py -3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt   # Windows: .venv/Scripts/python.exe
npm --prefix web install
cp .env.example .env            # then fill in the values listed in §4.3
.venv/bin/python -m scripts.warm_cache   # downloads ECAPA and TORGO; run once, on good wifi
make dev                        # starts all three processes
```

The Makefile calls the venv interpreter directly, so activating the venv is
optional. Windows: install make with `winget install ezwinports.make`; every
target runs from Git Bash, PowerShell, or cmd.

### 4.3 Environment variables (`.env.example` must contain exactly these)

```
PAYMENT_PROVIDER=stripe          # stripe | visa
STRIPE_SECRET_KEY=
VISA_CERT_PATH=
VISA_KEY_PATH=
VISA_USER_ID=
VISA_PASSWORD=
LLM_PROVIDER=anthropic           # anthropic | gemini
LLM_API_KEY=
MERCHANT_PORT=8000
ISSUER_PORT=8100
WEB_PORT=5173
MERCHANT_DB=./merchant.db
ISSUER_DB=./issuer.db
WEBAUTHN_RP_ID=localhost
WEBAUTHN_ORIGIN=http://localhost:5173
DATA_DIR=./data
```

### 4.4 Makefile targets (create these; do not invent others silently)

| Target | Does |
|---|---|
| `make dev` | Runs merchant API, issuer API, and Vite dev server concurrently |
| `make api` | Merchant service only, on `MERCHANT_PORT` |
| `make issuer` | Issuer service only, on `ISSUER_PORT` |
| `make web` | Frontend only, on `WEB_PORT` |
| `make seed` | Runs `scripts/seed_demo.py`: catalog, demo users, demo card tokens |
| `make eval` | Runs `scripts/run_eval.py`, writes `docs/eval_results.md` and charts |
| `make reset` | Deletes both `.db` files and re-seeds. Use between demo runs. |
| `make test` | Runs pytest (§13.4) |

---

## 5. Architecture

Three processes. The split between merchant and issuer is a *product* argument,
not just tidiness. Keep them genuinely separate: separate ports, separate
databases, no shared Python modules except pure utilities with no state.

```
┌─────────────┐  audio + cart   ┌──────────────┐   /v1/approve  ┌──────────────┐
│   web/      │ ──────────────▶ │  api/        │ ─────────────▶ │  issuer/     │
│ React :5173 │                 │ FastAPI :8000│                │ FastAPI :8100│
│             │ ◀────────────── │  (merchant)  │ ◀───────────── │              │
└─────────────┘  cart, receipt  └──────────────┘  {verified,    └──────────────┘
                                       │           transaction_id}     │
                                       ▼                               ▼
                                 merchant.db                      issuer.db
                              (catalog, orders)            (voice templates,
                                                            payment tokens,
                                                            verification log)
```

### 5.1 Who owns what (explicit, because this is easy to get wrong)

- **The issuer owns payment tokens.** Tokens never leave `issuer/`. The merchant
  never receives a token reference, not even a single-use one. This is stricter
  than real-world network tokenization and we do it because it makes the privacy
  boundary trivially demonstrable.
- **The issuer calls the payment provider.** `PaymentProvider` (§9.3) is
  instantiated and invoked inside `issuer/`, not inside `api/`. If you find
  `api/payments/`, move it to `issuer/payments/` and log the move.
- **The merchant owns the catalog, cart, order records, and the LLM shopping
  layer.** It originates `instruction_id` (a UUID) when the user confirms a cart,
  and passes it to the issuer. The issuer binds the verification result and the
  authorization to that `instruction_id`.
- **The merchant never sees:** the verification score, the threshold, which
  sound label was challenged, how many attempts occurred, whether the passkey
  fallback was used, or any part of the voice template.

### 5.2 Repo layout

```
timbre/
├── CLAUDE.md                 # this file
├── README.md                 # public-facing, written last
├── Makefile
├── requirements.txt
├── .env.example
├── .gitignore
├── api/                      # merchant service (port 8000)
│   ├── main.py
│   ├── catalog.py
│   ├── cart.py
│   ├── checkout.py           # originates instruction_id, calls issuer
│   └── llm.py                # n-best rerank, confirmation text, disputes
├── issuer/                   # issuer service (port 8100)
│   ├── main.py               # exposes /v1/approve, /v1/enroll
│   ├── config.py             # ALL tunable constants live here
│   ├── verification.py       # enroll / verify / adapt
│   ├── liveness.py           # challenge sequencing, replay detection
│   ├── webauthn_routes.py
│   ├── payments/
│   │   ├── base.py           # PaymentProvider ABC. DO NOT BYPASS.
│   │   ├── stripe_provider.py
│   │   └── visa_provider.py
│   └── db.py
├── ml/
│   ├── encoder.py            # the ONLY place the ECAPA model is loaded
│   ├── evaluate.py           # EER, ROC, drift simulation
│   └── baseline_asr.py       # the losing baseline, for demo contrast
├── web/
│   ├── src/pages/{Shop,Enroll,Checkout,Dashboard,Baseline}.jsx
│   ├── src/lib/audio.js      # capture and 16 kHz resample
│   └── src/lib/api.js
├── tests/
│   ├── test_verification.py
│   └── test_boundary.py      # asserts merchant response has exactly 2 keys
├── data/                     # gitignored, cached corpora
├── scripts/
│   ├── warm_cache.py
│   ├── seed_demo.py
│   └── run_eval.py
└── docs/
    ├── DECISIONS.md          # architecture decision records
    ├── DEMO.md               # the 90-second script
    └── eval_results.md       # generated by make eval
```

---

---

## 6. Stack and hard constraints

| Layer | Choice | Constraint |
|---|---|---|
| Backend | Python 3.12, FastAPI, uvicorn | SpeechBrain is Python. Do not add a second backend language. |
| Embeddings | `speechbrain/spkrec-ecapa-voxceleb` | 192-dim, CPU. Loaded exactly once, at import of `ml/encoder.py`. |
| Databases | SQLite, two files: `merchant.db`, `issuer.db` | No Postgres, no Docker, no ORM, no migration framework. Raw SQL. |
| Frontend | Vite plus React, plain CSS | No Next.js, no component library, no Tailwind. |
| Audio capture | MediaRecorder plus OfflineAudioContext | Resample client-side to 16 kHz mono before upload. |
| ASR | faster-whisper `small` | Shopping intent only. Never identity. Never imported under `issuer/`. |
| LLM | Anthropic or Gemini, chosen by `LLM_PROVIDER` | Strict JSON output, `temperature=0`, parse wrapped in try/except. |
| Passkeys | SimpleWebAuthn | See the RP ID warning in §12. |
| Payments | `PaymentProvider` ABC in `issuer/payments/base.py` | Concrete provider chosen by `PAYMENT_PROVIDER`. Never imported outside that package. |

Adding any dependency not listed here requires a Change Log entry (§14) stating
what it replaces and why the existing stack could not do it.

---

---

## 13. Conventions for Claude

### 13.1 How to work here

- **Read before writing.** Check actual file contents. Do not assume §5.2 exists.
- **Small, verifiable steps.** After each change, state the exact command or
  click-path that confirms it worked.
- **Named constants, not literals.** Every tunable lives in `issuer/config.py`.
- **No new dependencies without a Change Log entry** stating why.
- **No speculative abstraction.** This is a 36-hour build. Write two concrete
  implementations before extracting an interface. The single exception is
  `PaymentProvider`, which is required up front because the provider will change.
- **Never commit** `.env`, `data/`, `models/`, `*.db`, or any audio file.
- **Fail loudly.** No bare `except:` that swallows an error. A silent failure
  during the demo is worse than a crash, because you cannot debug what you
  cannot see.
- **Our own UI must be accessible.** Keyboard reachable in full, visible focus
  rings, every control labeled, contrast at or above 4.5:1, touch targets at or
  above 44 px, no meaning carried by color alone, and live regions announcing
  verification results. A judge will tab through it. Shipping an inaccessible
  accessibility project ends the conversation.

### 13.2 Commit messages

```
<area>: <imperative summary>

area is one of: issuer, api, web, ml, docs, infra, tests
```

### 13.3 When you are blocked or uncertain

Do not guess at external API shapes or invent endpoint names. State what you
need, propose the smallest stub that unblocks progress, mark the stub with a
`# STUB:` comment, and log it in §14 so it does not ship by accident.

### 13.4 Testing

Minimal but non-optional. `make test` runs:

- `tests/test_verification.py`: enrollment cohesion math, threshold computation,
  adaptation clamp (assert the template cannot move more than `MAX_DRIFT` in one
  update), and replay rejection.
- `tests/test_boundary.py`: asserts the merchant-facing response body has
  exactly the keys `{"verified", "transaction_id"}`. This test is the
  machine-readable form of non-negotiable §2.5. **If it fails, the build is
  broken, regardless of what else works.**

---

---

## 15. Open questions

- [ ] Does the Visa table have pre-provisioned Intelligent Commerce credentials
      for hackers? Ask in hour 1, not Saturday night.
- [ ] Which HackGT tracks accept this submission alongside the Visa challenge,
      and does the event allow one project in multiple categories?
- [ ] Does TORGO `headMic` audio contain enough material per speaker for
      5-recording enrollment plus a held-out test set? Verify after loading.
- [ ] Exact speaker count in the HuggingFace subset. Print it, do not assume 15.
- [ ] Is a single `THRESHOLD_MARGIN` adequate, or should it scale with measured
      spread?
- [ ] Do we have anyone with lived experience to talk to before Saturday?
      Georgia Tech CIDI is on campus.
- [ ] What catalog do we use for the 20 real products?

---


---

## Where the rest lives

- Verification algorithm, thresholds, adaptation, liveness: `docs/ALGORITHM.md` §7
- TORGO data rules and speaker parsing: `docs/ALGORITHM.md` §8
- Payments and the Visa situation: `docs/ALGORITHM.md` §9
- Generative AI requirements: `docs/ALGORITHM.md` §10
- Prior art, do not overclaim: `docs/CONTEXT.md` §11
- Known issues and workarounds: `docs/CONTEXT.md` §12
- Demo script and judge answers: `docs/CONTEXT.md` §16
- Glossary: `docs/CONTEXT.md` §17
- Change log: `docs/CHANGELOG.md` §14

Section numbers are preserved from the original single-file version, so a
reference like "non-negotiable §2.5" always means the same thing across files.
