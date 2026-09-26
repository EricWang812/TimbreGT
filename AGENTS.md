# AGENTS.md - Timbre

## Handoff (read first; updated 2026-09-25, moved from Claude Code to Codex)

**First action:** read this file, then `docs/CHANGELOG.md` (newest first), `docs/DECISIONS.md` (ADR 2-4), and `docs/CONTEXT.md` §12. Read `docs/ALGORITHM.md` before touching `issuer/`, `ml/`, or payments. Then give the person running Codex a short summary: what is done, what is next, open decisions.

**Done (Phases 0-6, 96 tests pass via `make test` as of Phase 8):** three services (merchant :8000, issuer :8100, Vite web :5173); privacy boundary (merchant learns only `{verified, transaction_id}`, enforced by tests); accessible storefront + bank widget; ECAPA enrollment, interleaved (ADR 4), held-out spread thresholds (ADR 3); voice challenge 2-of-3 with replay check and 2-attempt fallback; real WebAuthn passkeys; Stripe test-mode payments. Stubs remaining: enrollment/passkey registration have no auth (demo sign-in). `visa_provider` is built on the CyberSource sandbox (ADR 13) but not yet run against live sandbox keys.

**Also done since the Codex handoff (109 tests):** Phase 8 run (`make eval`; ADR 3: EER 6.7% control, 8.8% dysarthric). Phase 7 code (merchant n-best ASR, LLM rerank, keyword fallback, confirm-before-add UI), checked against real Whisper. Baseline page (`#/baseline`, `make baseline`). Phase 9 adaptation in the live voice path plus Dashboard drift chart (`#/dashboard`, `make drift`). Numbers are in the 2026-09-26 00:40 CHANGELOG entry. Each demo machine needs `scripts.warm_asr`, then `make eval && make baseline && make drift` once (outputs are gitignored).

**Agentic voice shopping, Feature 1 (OpenAI transcription, 2026-09-26; 137 tests pass):** Added a separate merchant endpoint, `POST /agentic-shopping/transcribe`, backed only by `gpt-4o-transcribe`. It accepts the existing browser recorder's mono 16 kHz WAV, validates empty, silent, malformed, oversized, wrong-rate, and overlong recordings before transmission, and returns `{transcript}` without stripping, normalizing, or interpreting OpenAI's text. Provider failures are sanitized and never change the cart. The key is backend-only as `OPENAI_API_KEY`. The existing `/shopping/voice` and `/shopping/text` routes, `api/asr.py` local Whisper pipeline, reranker, and current voice-shopping UI remain registered and unchanged. Feature 1 is backend-only; no current user flow calls the new endpoint yet. Verified with 5 focused tests, the full 137-test suite, and the unchanged frontend production build.

**Agentic voice shopping, Feature 2 (structured intent extraction, 2026-09-26; 142 tests pass):** Added a separate `POST /agentic-shopping/intent` stage backed by OpenAI `gpt-4.1-mini` and strict JSON Schema Structured Outputs. It accepts a raw transcript, returns that text unchanged as `rawTranscript`, and returns a validated `extractedIntent` with product, brand, budget, quantity, size, color, merchant, use case, requirements, preferences, missing fields, confidence, exact supporting source text, and material ambiguities. Likely recognition errors keep both what was heard and the proposed interpretation, so nothing uncertain is silently confirmed. The service treats the transcript as untrusted data, sets OpenAI response storage off, sanitizes provider or malformed-output failures, and never searches, mutates the cart, contacts the issuer, or checks out. Features 1 and 2 are backend-only and remain separate calls. At this stage, ambiguity resolution and UI integration were not built. The existing Whisper routes and files remain unchanged. Verified with 5 new focused tests, all 10 agentic tests, the full 142-test suite, and the unchanged frontend production build.

**Agentic voice shopping, Feature 3 (ambiguity resolution, revised 2026-09-26; 153 tests pass):** Added deterministic, backend-only clarification state through `POST /agentic-shopping/clarifications` and `POST /agentic-shopping/clarifications/answer`. Product, quantity, and maximum price are mandatory and always require confirmation or correction. Brand, size, color, merchant, use case, important requirements, and optional preferences are optional when absent, but every one supplied in the request is also verified before finalization. Each question is short and field-specific, offers Yes/No when there is a proposed interpretation, and turns No into a correction prompt for only that field. Confirmed and corrected values live in `resolvedValues`; `rawTranscript`, `extractedIntent`, and per-field `clarificationAnswers` remain separate, so the original OpenAI interpretation is never overwritten and users do not repeat the whole request. Invalid, stale, unsupported, empty, or unrelated answers receive 422 and cannot mutate the cart. State is client-carried to match the existing React local-state architecture; no new global state library, database, OpenAI call, or dependency was added. The existing Whisper, cart, issuer, authentication, and checkout paths remain unchanged. Verified through all 21 agentic tests, dependency install/check, the full 153-test suite, and the unchanged frontend production build.

**Agentic voice shopping, Feature 4 (final structured intent, revised 2026-09-26; 153 tests pass):** Added `POST /agentic-shopping/finalize` and a deterministic finalization service. It recomputes clarification state instead of trusting client-supplied `complete`, pending questions, or resolved values; refuses pending, missing, unclear, and non-shopping requests with 409; and emits a typed `finalIntent` only after Feature 3 verification. Product, maximum price, and quantity are required in the final schema. Brand, size, color, merchant, use case, important requirements, and optional preferences remain nullable or empty when they were not requested. Numeric corrections are normalized and must be finite, nonnegative prices or positive whole quantities. The response still carries the exact raw transcript, original extraction, and clarification answers, so finalization never erases evidence. This stage does not call OpenAI, search, mutate the cart, contact the issuer, authenticate, or check out. At this stage, commerce execution and agentic UI integration were not built. Existing Whisper and purchase paths remain unchanged. Verified with all 21 agentic tests, dependency install/check, the full 153-test suite, and the unchanged frontend build.

**Agentic voice shopping, Feature 5 (commerce agent and prepared cart, 2026-09-26; 159 tests pass):** Added `POST /agentic-shopping/commerce/prepare-cart` backed by `api/commerce_agent.py`. It consumes the complete Feature 4 request, searches the existing seeded catalog, applies hard product, brand, size, merchant, currency, quantity, line-budget, and important-requirement constraints, ranks remaining products deterministically, selects the best match, merges the requested quantity into caller-supplied existing cart lines, and delegates all prices, tax, shipping, and totals to the existing `api/cart.py` pricer. Unsupported color variants, foreign currencies, wrong merchants, over-budget products, invalid quantities, and unsatisfied requirements return `no_matches` or a sanitized conflict instead of a guess. Use case and optional preferences can affect ranking but are disclosed as unverified when the catalog lacks supporting metadata. `no_matches` returns the original cart unchanged. The response is a complete server-priced `cart_ready` payload; `web/src/lib/api.js` exposes an additive adapter for the existing CartProvider to apply in the future agentic UI. This endpoint cannot create an order, instruction ID, issuer session, authentication challenge, or payment. Existing Whisper and checkout behavior remain unchanged. Verified with 6 new tests, all 27 agentic tests, dependency install/check, the full 159-test suite, and the unchanged frontend production build.

**Agentic voice shopping, Feature 6 (existing cart integration, 2026-09-26; 159 tests pass):** Extended the existing browser `CartProvider` with one validated `replaceLines` operation and connected the Feature 5 result to it. The UI sends a snapshot of current lines, applies only a successful `cart_ready` payload, and checks that the cart did not change during the request before replacement. Invalid output, no matches, canceled work, request failure, and concurrent cart edits leave the prior cart intact. Pricing still comes exclusively from `api/cart.py`; no second cart store or pricing path was introduced.

**Agentic voice shopping, Feature 7 (purchase boundary, 2026-09-26; 159 tests pass):** The agent stops at Cart Ready. Its only next actions are Review cart and Continue to checkout, which enter the existing cart drawer and `#/checkout` route. The existing checkout creates the instruction, invokes the issuer authentication widget, and completes payment after authorization. No agentic route or frontend helper can create an order, contact the issuer, authenticate, approve, or pay. The existing merchant boundary tests still pass.

**Agentic voice shopping, Feature 8 (complete additive UI, 2026-09-26; 159 tests pass):** Added a separate full-request panel below the unchanged Whisper panel. It reuses the existing recorder, calls transcription and intent extraction separately, shows the exact raw transcript and extracted fields, asks one material confirmation at a time, accepts a correction for only the rejected field, shows the finalized item, quantity, and price, runs commerce, and presents Cart Ready. The state remains local to the component and preserves raw transcript, original extraction, clarification state, corrections, final intent, and commerce result as distinct values. The panel was verified in the local browser and accessibility tree alongside the original `VoiceShopping` component.

**Agentic voice shopping, Feature 9 (failure and cancellation handling, 2026-09-26; 159 tests pass):** The new UI handles microphone denial or capture failure through the shared recorder, API and network errors through abortable requests, server validation and empty-speech messages, malformed or unavailable OpenAI results, unresolved fields, no catalog matches, bad prepared carts, and cart races. Cancel aborts the active request and recording. Failures retain visible session evidence when useful and do not modify the existing cart. A new request resets only the agentic session.

**Agentic voice shopping, Feature 10 (final verification, 2026-09-26; 159 tests pass):** Reinstalled all pinned Python requirements, confirmed no broken packages, ran all 27 focused agentic tests, ran the complete 159-test suite with only the two existing SpeechBrain warnings, rebuilt the 66-module frontend production bundle, ran `git diff --check`, and inspected the combined shopping UI in a local browser. No new dependency was required. A live OpenAI round trip remains environment-dependent and requires a valid backend-only `OPENAI_API_KEY`.

**Live text-stage simulations (2026-09-26):** Skipped transcription and sent two supplied transcripts directly to the live OpenAI intent endpoint. `Purchase me 1 banana and i only want to spend at most $20` produced high-confidence banana, quantity 1, and USD 20 fields; asked for confirmation of all three mandatory fields; finalized successfully; selected Dole Organic Bananas at $2.99; and returned a server-priced `cart_ready` result. `I want boys headphones at $400` did not silently accept `boys`: it assigned medium confidence, asked `Should I use use case boys?`, and after No asked only `What use case did you mean?`. It also required quantity confirmation. This meets the uncertainty and clarification safety behavior, but semantic repair is incomplete: the model did not propose Bose as a likely brand, classified `boys` as both use case and optional preference, and produced duplicate questions.

**Agentic clarification redesign (ADR 10, 2026-09-26; 174 tests pass):** Replaced confirm-every-field with ask-only-when-unsure. High-confidence values are accepted silently; only the product is required; unstated quantity is 1 and unstated budget is no limit, both shown as assumptions. Uncertain values get one Yes/No each, one question per field and per span of words. The planned boys/Bose repair is implemented deterministically (catalog brands only, never auto-accepted, same words set aside elsewhere, declining restores them), and a store brand the speaker never said is ignored. The intent prompt now sees the catalog. Commerce explains no-match reasons, treats color as soft, prefers closer names, matches split compounds. The UI applies a clear request straight to the cart and offers Undo. Live text runs: of 11 shopping transcripts, 8 needed no question and 3 needed one. Not yet spoken through the browser after this change.

**Agentic quantity reasoning (2026-09-26):** "As much X as I can under $10" fills the budget (floor of limit over unit price, capped at MAX_QUANTITY), "under $2 each" limits one unit, "the cheapest" picks the lowest price among relevant matches, and package words count packages ("a dozen eggs" is 1 carton). Live: yogurt under $10 gives 6 for $8.94, soup for $20 gives 13, pasta for $15 gives 7, with no questions.

**Agentic baskets (ADR 11, 2026-09-26; 192 tests pass):** The agentic panel now uses `/agentic-shopping/basket/*`. One request can name several items and ask for meals ("stuff for tuna salad, and two cokes, under 20 bucks"). Named items go straight to the cart with Undo; meal picks and unsaid items show a review list (Remove, Put back, Add to cart). Meal ingredients must be real catalog ids, unknown ones are listed as not sold here, and a basket budget is shared with "as many as fit" items taking what is left. Recording limit is 25 s on this panel only. Not yet spoken through the browser.

**Agentic affordability language fix (2026-09-26; 194 tests pass):** Fixed requests such as `Very cheap yogurt.` that previously got stuck with `No Greek Yogurt, Nonfat Plain here is described as cheap.` OpenAI had correctly set `preferCheapest` but also emitted `cheap` as a hard `importantRequirement`, so commerce searched product descriptions for the word. Commerce now deterministically treats cheap, cheapest, affordable, inexpensive, economical, budget-friendly, low-cost, lowest-price, best-price, and least-expensive language as price ranking rather than catalog metadata. It still preserves real properties in mixed phrases, so `cheap organic yogurt` requires organic, and unrelated constraints such as `low sodium` remain hard requirements. The extraction prompt now forbids duplicating affordability words into requirements or preferences. This guard is shared by single-item and basket preparation. A live run of the exact transcript returned `cart_ready` with Chobani Greek Yogurt, Nonfat Plain. Existing Whisper, checkout, issuer, authentication, and payment behavior is unchanged.

**Header voice launcher and Whisper fallback (2026-09-26; 194 tests pass):** The header `Shop by voice` button now starts the additive agentic recorder instead of only focusing the legacy panel. It navigates to the shop when needed, scrolls to the agentic panel, focuses its microphone control, and starts recording. If the agentic panel is not mounted, it starts the unchanged Whisper recorder. If an agentic stage returns 503 after recording, the same WAV is handed to `VoiceShopping`, which runs the existing `/shopping/voice` Whisper path and keeps its normal confirmation-before-add UI, so the shopper does not repeat the request. An active recorder or clarification is focused rather than toggled or competing with a second recording.

## Multi-Market Implementation Progress

### Feature 1: Market Owner Authentication

**Status:** Implemented on 2026-09-26.

**Changes:** Added merchant-side market-owner account registration, login, logout, current-session lookup, and a reusable `current_market_owner` FastAPI dependency for future protected market routes. The issuer/cardholder identity system remains separate and unchanged. Registration creates only an account, never a market, so this feature cannot create anonymous or orphan markets.

**Files added:** `api/market_auth.py`, `tests/test_market_auth.py`.

**Files modified:** `api/db.py`, `api/config.py`, `api/main.py`, `.env.example`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added `accounts` with case-insensitive unique email, salted scrypt password hash, role, and creation time. Added `market_sessions` with only a SHA-256 token digest, owner foreign key with cascade deletion, creation time, expiry, and an owner lookup index. The schema reserves `BUYER` as a future role, but buyer registration and login are not implemented.

**Routes:** `POST /market-auth/register`, `POST /market-auth/login`, `POST /market-auth/logout`, and `GET /market-auth/me`. Registration and login set a random HttpOnly, SameSite=Lax session cookie. Logout revokes its server-side session. Missing, invalid, expired, or non-market-owner sessions receive 401. Duplicate emails receive 409, malformed emails and passwords shorter than 12 characters receive 422, and login failures use one generic error.

**Authorization/security:** Future market-management routes can require the exported `current_market_owner` dependency, which resolves the authenticated account server-side and enforces the `MARKET_OWNER` role. Raw session tokens and plaintext passwords are never stored. `MARKET_SESSION_TTL_SECONDS` defaults to 12 hours. `MARKET_SESSION_COOKIE_SECURE` defaults to false for the local HTTP demo and must be true behind production HTTPS. Credentialed CORS remains restricted to the configured Timbre web origin. This account authenticates marketplace administration only and does not replace or bypass Timbre purchase authorization.

**Verification:** `.venv/bin/python -m pip install -r requirements.txt` and `pip check` pass with no new dependency. The 40-test focused authentication, health, CORS, and merchant/issuer boundary run passes. All 7 issuer import guards pass in isolation. The complete suite reports 199 passed and 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer import guards on this macOS runtime; both failing guards pass together in their isolated file. `npm run build` passes with 66 modules. `git diff --check` passes.

**Known limitations:** No market-owner login UI, password reset, email verification, rate limiting, or account administration exists yet. Cookies require the secure flag to be enabled for production HTTPS.

### Feature 2: Market Creation

**Status:** Implemented on 2026-09-26.

**Changes:** Added authenticated creation of persistent markets. The request accepts only a required market name. The server derives the owner relationship from the authenticated Feature 1 session and returns the created market with its generated ID, normalized name, owner account ID, and creation time.

**Files added:** `api/markets.py`, `tests/test_markets.py`.

**Files modified:** `api/db.py`, `api/main.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added `markets` with required ID, nonblank name, required `owner_account_id` foreign key, and creation time, plus an owner lookup index. Owner deletion is restricted while a market references it. A database trigger rejects missing accounts and accounts whose role is not `MARKET_OWNER`, so the ownership invariant also holds outside the route.

**Routes:** Added `POST /markets`. It requires the existing market-owner session dependency. The request schema forbids extra fields, including a client-supplied owner ID. Names are trimmed and internal whitespace is normalized; blank names receive 422. Successful creation returns 201.

**Authorization/security:** Anonymous requests receive 401 and write nothing. The authenticated account is always persisted as the owner. A caller cannot create a market for another owner by supplying an account ID. This authentication remains separate from issuer/cardholder identity and Timbre purchase authorization.

**Verification:** Reinstalled all pinned requirements and ran `pip check` with no missing or broken packages. The focused market, authentication, health, CORS, and boundary run passes all 47 tests. It covers creation, persistence, owner assignment, anonymous rejection, owner spoofing rejection, invalid names, buyer-role rejection, and missing-account rejection. All 7 issuer import guards pass in isolation. The complete suite reports 206 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; both pass in isolation. The 66-module frontend production build and `git diff --check` pass.

**Known limitations:** There is no market creation UI or market listing endpoint yet. Product, fulfillment, order, and agent integration features remain unimplemented.

### Feature 3: Market Branding

**Status:** Implemented on 2026-09-26.

**Changes:** Markets now have a required name, a customizable six-digit hex primary color, and an optional logo reference. Added an owner-only branding update endpoint, a public branding read endpoint, and a public `#/markets/{marketId}` view. The view displays the configured logo or generated one-to-two-letter initials when no logo exists. The market color is confined to a decorative card border and logo border, so it neither changes global Timbre styles nor controls text contrast.

**Files added:** `web/src/pages/MarketStorefront.jsx`.

**Files modified:** `api/db.py`, `api/main.py`, `api/markets.py`, `tests/test_markets.py`, `web/src/App.jsx`, `web/src/components/PageHeading.jsx`, `web/src/lib/api.js`, `web/src/lib/router.js`, `web/src/styles.css`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added `primary_color` with default `#126B5B` and nullable `logo_url` to `markets`. `init_db()` performs additive `ALTER TABLE` migration when opening a database created by Feature 2, preserving existing market rows and applying the default color.

**Routes/UI:** Added public `GET /markets/{market_id}` and owner-only `PATCH /markets/{market_id}/branding`. The patch accepts any combination of `name`, `primaryColor`, and `logoUrl`, requires at least one supplied field, and permits `logoUrl: null` to restore the initials placeholder. Public responses omit `ownerAccountId`. The hash route `#/markets/{marketId}` loads and displays the scoped branding, handles loading and missing-market errors, and sets the page title to the market name.

**Image handling and validation:** No upload/storage dependency existed, so branding follows the catalog's existing URL-reference approach and stores no image bytes. Logo references must be HTTPS URLs or root-relative static paths; HTTP, protocol-relative, JavaScript, data, and malformed values are rejected. Theme colors must be exact six-digit hex values and are normalized to uppercase. Market names remain required and normalized.

**Authorization/security:** Only the authenticated owner can change a market. The update matches both market ID and authenticated `owner_account_id` in one SQL statement; another owner receives 404 and cannot infer a private management distinction. Public branding exposes storefront fields only, not owner account IDs. PATCH was added to the existing origin-restricted credentialed CORS policy.

**Verification:** Reinstalled all pinned requirements and ran `pip check` successfully; no package was added. The focused market, authentication, health, CORS, and boundary run passes all 60 tests, including ownership, validation, logo clearing, public-field privacy, placeholder generation, and migration of a Feature 2 database. The complete suite reports 219 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend production build, Python compilation, and `git diff --check` pass.

**Known limitations:** Market owners configure branding through the API because an owner administration UI is not built yet. Logo upload is not implemented; owners reference an existing HTTPS image or a static asset path. The storefront branding page does not list products yet.

### Feature 4: Product Creation

**Status:** Implemented on 2026-09-26.

**Changes:** Added authenticated product creation for a market owned by the current account. A request supplies only required `name` and numeric `price`, plus optional `photoUrl`. Names are normalized, prices permit zero but never negative values, accept at most two decimal places, and are persisted as exact integer cents. The response includes generated product ID, market ID, normalized name, decimal price, integer cents, optional photo URL, and creation time.

**Files added:** `api/market_products.py`, `tests/test_market_products.py`.

**Files modified:** `api/db.py`, `api/main.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added `market_products` with required ID, required market foreign key, nonblank name, nonnegative integer `price_cents`, optional `photo_url`, and creation time, plus a market lookup index. Market deletion is restricted while products reference it.

**Legacy catalog decision:** The existing `products` table remains the read-only seeded Seaside demo catalog used by the working cart and voice-shopping paths. It requires brand, size, category, image, and image-credit values that Feature 4 does not require. Rather than fabricate data or destructively rebuild that table, seller-created products use the additive `market_products` table. A later storefront/commerce adapter can combine the sources when those features are implemented.

**Routes:** Added owner-authenticated `POST /markets/{market_id}/products`. The market comes only from the path, and extra request fields such as a client-supplied `marketId` are rejected. The route verifies `market.id` and `market.owner_account_id` together inside the insertion transaction, then returns 201. Missing markets and markets owned by another account return 404 without writing.

**Image handling and validation:** Product photos follow the existing URL-reference convention and remain optional. Accepted references are HTTPS URLs or root-relative static paths. Empty strings become no photo. HTTP, protocol-relative, JavaScript, data, and malformed references are rejected. No image bytes or new storage dependency were added.

**Authorization/security:** Anonymous requests receive 401. An authenticated owner can add a product only to a market they own. The backend never trusts a client-provided ownership relationship, and a failed authorization or validation leaves all market products unchanged. Issuer identity, Timbre purchase authentication, the legacy catalog, cart, checkout, and payment paths remain unchanged.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused product, market, authentication, health, CORS, and boundary run passes all 77 tests. It covers persistence, exact cents, optional photos, zero price, static and HTTPS photos, anonymous rejection, cross-owner rejection, missing markets, required fields, negative and over-precision prices, nonnumeric and boolean prices, unsafe photo references, and market-ID spoofing. The complete suite reports 236 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Product management is API-only and products do not appear in the storefront yet. Seller products are not yet consumed by the existing cart or commerce agent.

### Feature 5: Product Editing and Removal

**Status:** Implemented on 2026-09-26.

**Changes:** Added authenticated owner product listing, partial editing, and removal. Owners can list products in one of their markets, update any combination of name, price, and photo reference, clear a photo with `null`, and delete a product. The product ID, market ID, and creation time remain stable through edits. Removal is permanent within this feature's explicitly requested scope.

**Files modified:** `api/main.py`, `api/market_products.py`, `tests/test_market_products.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Routes:** Added owner-only `GET /markets/{market_id}/products`, `PATCH /markets/{market_id}/products/{product_id}`, and `DELETE /markets/{market_id}/products/{product_id}`. PATCH requires at least one supported field and reuses Feature 4 name, price, and photo validation. DELETE returns 204; a repeated or unknown deletion returns 404.

**Authorization/security:** Every operation first verifies that the authenticated account owns the path market, then constrains the product mutation or deletion by both product ID and market ID. Another owner cannot list, edit, or delete products from a different market, even when supplying its exact IDs. Anonymous requests receive 401. Invalid edits, wrong-market IDs, unauthorized attempts, and repeat deletes do not alter any product.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused product, market, authentication, health, CORS, and boundary run passes all 91 tests. It covers owner listing, all-field edits, photo clearing, invalid-edit preservation, cross-owner list/edit/delete rejection, deletion, repeat deletion, and anonymous management rejection. The complete suite reports 250 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Product management has no owner UI or public storefront listing yet. Seller products remain separate from the seeded catalog and are not yet consumed by cart or agent paths.

### Feature 6: Product Quantity and Unit Support

**Status:** Implemented on 2026-09-26.

**Changes:** Market products can now optionally carry a measured quantity and canonical unit. Both fields are required together when either is supplied, while ordinary individually sold products can remain unmeasured. Supported units are weight (`mg`, `g`, `kg`, `oz`, `lb`), volume (`mL`, `L`, `fl oz`, `gal`), and `count`. Quantity is numeric, positive, and stored separately from the display unit. Creation accepts a complete measurement; editing can add, change, or clear both fields, and can change just one value when the product already has a valid matching value.

**Files modified:** `api/db.py`, `api/market_products.py`, `tests/test_market_products.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added nullable `quantity_value` and `quantity_unit` columns to `market_products`, a complete-pair and positive-value constraint for new databases, and insert/update triggers for the same invariant. `init_db()` additively migrates Feature 4/5 databases before installing the triggers, leaving their existing product rows unmeasured and valid.

**Routes:** Existing owner-only product create, list, and PATCH routes now include `quantity` and `unit` in their product response and accept the fields in create/PATCH bodies. The route validates the pair before writing. An incomplete pair, nonnumeric or nonpositive quantity, or a noncanonical unit returns 422 without changing the product.

**Authorization/security:** Measurement changes retain the existing owner-to-market-to-product backend ownership checks. Database constraints and triggers preserve the quantity invariant even outside the API. This feature adds no path to the legacy seeded catalog, cart, commerce agent, checkout, or purchase authorization flow.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused product and market run passes all 73 tests, including valid weight, volume, and count storage, unmeasured products, create and update pair validation, clearing, Feature 5 database migration, and direct database invariant enforcement. The complete suite reports 272 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Units are stored and validated but are not yet converted or compared across dimensions. Product management remains API-only, and market products remain separate from the legacy catalog, cart, and agent paths.

### Feature 7: Quantity Per Dollar

**Status:** Implemented on 2026-09-26.

**Changes:** Measured market-product responses now include a derived `quantityPerDollar` value, calculated as declared quantity divided by price in USD. It uses the product's existing `unit`, so `2 lb` at `$4` yields `0.5` in `lb/$`, and `750 mL` at `$3` yields `250` in `mL/$`. The value is calculated on every create, read, and update response, never accepted from a client or persisted in the database.

**Files modified:** `api/market_products.py`, `tests/test_market_products.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** No schema changes. The calculation deliberately uses `quantity_value` and integer `price_cents` already stored by Feature 6, so it remains current after a price or quantity edit and cannot become stale.

**Routes:** Existing owner-authenticated product create, list, and PATCH responses now include `quantityPerDollar`. It is `null` when a product has no measurement or its price is zero, avoiding an invalid division. The product's existing `unit` supplies the accompanying display dimension.

**Authorization/security:** The value is server-derived from owner-protected product data. Clients cannot supply or overwrite it, and no catalog, cart, commerce, checkout, or purchase-authorization behavior changed.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused product and market run passes all 78 tests, including pound, milliliter, and count examples, zero-price and unmeasured null cases, list/PATCH recalculation, and confirmation that no derived database column exists. The complete suite reports 277 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Values remain expressed in the seller-entered unit alongside the normalized value. Incompatible dimensions are not compared. Product management remains API-only, and market products remain separate from the legacy catalog, cart, and agent paths.

### Feature 8: Unit Normalization

**Status:** Implemented on 2026-09-26.

**Changes:** Added a pure market-unit normalization helper that converts weight to milligrams, volume to milliliters, and count to count. Product responses retain the seller-entered `quantity` and `unit`, and now also expose `normalizedQuantity`, `normalizedUnit`, `quantityDimension`, and `normalizedQuantityPerDollar`. This lets later catalog logic compare only quantities in the same physical dimension while preserving user-friendly display units.

**Files added:** `api/market_units.py`.

**Files modified:** `api/market_products.py`, `tests/test_market_products.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** No schema changes. Normalized values are derived at response time from the Feature 6 quantity fields and the Feature 7 integer-cent price, so no duplicate mutable quantity or pricing data is stored.

**Routes:** Existing owner-authenticated product create, list, and PATCH responses include the new normalization fields. Unmeasured products return `null` for all normalized values. `mg`, `g`, `kg`, `oz`, and `lb` normalize only within the `weight` dimension; `mL`, `L`, `fl oz`, and `gal` only within `volume`; and `count` is its own `count` dimension.

**Comparison safety:** The exported `units_are_compatible` helper returns true only for two units in the same dimension. It returns false for weight versus volume, count versus either measurement dimension, and absent units. No function converts or ranks incompatible values as though they were equivalent.

**Authorization/security:** Normalized response values are server-derived and cannot be client-supplied or persisted independently. Existing product ownership checks and the separation from legacy cart, commerce, checkout, and purchase authorization paths remain unchanged.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused product and market run passes all 86 tests, including pound and gram weight conversions, liter and gallon volume conversions, count preservation, normalized per-dollar values, absent measurements, and incompatible-unit rejection. The complete suite reports 285 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Normalization is available to later catalog and commerce code, but this feature does not search, rank, or merge products. Product management remains API-only, and seller products remain separate from the legacy catalog, cart, and agent paths.

### Feature 9: Buyer Login

**Status:** Implemented on 2026-09-26.

**Changes:** Added buyer registration, login, logout, current-session lookup, and an exported `current_buyer` dependency. Buyer accounts reuse the existing `accounts` and `market_sessions` tables, password hashing, expiry cleanup, and token-digest storage. They use a separate HttpOnly `timbre_buyer_session` cookie, so buyer logout does not revoke a simultaneous market-owner session in the same browser.

**Files added:** `api/buyer_auth.py`, `tests/test_buyer_auth.py`.

**Files modified:** `api/config.py`, `api/main.py`, `api/market_auth.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** No schema migration. Feature 1 already reserved the `BUYER` account role. The existing `accounts` table now has active buyer rows, while the existing session table continues to store only a SHA-256 digest, account ID, expiry, and creation timestamp.

**Routes:** Added `POST /buyer-auth/register`, `POST /buyer-auth/login`, `POST /buyer-auth/logout`, and `GET /buyer-auth/me`. Registration and login issue the buyer session cookie. Inputs retain the existing normalized email and 12-to-128-character password rules. Duplicate email returns 409; invalid credentials return the same generic 401 response used by market-owner login.

**Authorization/security:** Buyer login uses the same salted scrypt password hashes and 12-hour expiry setting as market-owner login, with a distinct cookie name. The shared role-aware server dependency checks the expected account role at query time. A buyer cannot access market-owner routes or create markets, and a market owner cannot use buyer routes. Buyer authentication remains a shopping-session identity only: it does not modify the existing Timbre voice/passkey purchase authorization or authorize payment.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused buyer, owner, market, and product run passes all 100 tests, including buyer registration, session cookies, login, logout, expiration, role isolation, separate owner and buyer cookie behavior, dependency protection, invalid input, and duplicate email handling. The complete suite reports 292 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Buyer login is API-only. Buyer profiles, order history, fulfillment selection, and checkout linkage are not implemented yet. The existing Timbre authorization remains separate by design.

### Feature 10: Buyer Addresses

**Status:** Implemented on 2026-09-26.

**Changes:** Added private shipping-address creation and listing for authenticated buyers. An address includes recipient name, address line 1, optional address line 2, city, state or region, postal code, and country. Required fields are whitespace-normalized and nonblank; an omitted or blank second line is stored as `null`.

**Files added:** `api/buyer_addresses.py`, `tests/test_buyer_addresses.py`.

**Files modified:** `api/db.py`, `api/main.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added `buyer_addresses` with a required buyer-account foreign key, required shipping fields, nullable second line, creation timestamp, and buyer lookup index. A database trigger requires the linked account role to be `BUYER`, so an address cannot be inserted for a market owner through direct database access.

**Routes:** Added buyer-authenticated `POST /buyer/addresses` and `GET /buyer/addresses`. The server derives the address owner solely from the buyer session, forbids client-supplied ownership fields, and returns only the current buyer's addresses. Browsing requires no address, and checkout does not yet consume one.

**Authorization/security:** Addresses are private buyer data. Anonymous requests receive 401, another buyer receives an empty list rather than the first buyer's records, and address rows cannot be assigned to another account by request data. Existing market-owner authorization and Timbre voice/passkey purchase authorization remain separate and unchanged.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused address, buyer, owner, market, and product run passes all 113 tests, including persistence, normalization, optional line two, private list scoping, anonymous rejection, validation and no-write behavior, ownership spoofing rejection, and direct database buyer-role enforcement. The complete suite reports 305 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Addresses are API-only and cannot yet be edited or removed. Feature 13 now requires a saved address only when a buyer selects shipping, but the legacy checkout has no market mapping and therefore intentionally does not consume that selection yet. Market shipping configuration is implemented in Feature 12.

### Feature 11: Market Pickup Settings

**Status:** Implemented on 2026-09-26.

**Changes:** Market owners can now save a real pickup address, enable pickup only when an address exists, disable pickup while retaining the saved address, and remove the address only after pickup is disabled. The address includes street line 1, optional line 2, city, state or region, postal code, and country. Owners may save the address and enable pickup in one atomic request.

**Files modified:** `api/db.py`, `api/markets.py`, `tests/test_markets.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added nullable-by-relationship `market_pickup_addresses`, keyed one-to-one by market ID, plus a persisted `markets.pickup_enabled` flag. `init_db()` additively adds the flag for Feature 2 through Feature 10 databases. Database triggers reject enabling pickup without an address, creating a market with pickup enabled before an address can exist, and deleting an address while its market remains pickup-enabled.

**Routes:** Added owner-only `GET /markets/{market_id}/pickup-settings` and `PATCH /markets/{market_id}/pickup-settings`. PATCH accepts `pickupEnabled` and/or `pickupAddress`; it returns 422 for no supplied setting, incomplete address data, enabling without an address, or removing the active address. These management routes are private; buyer-facing pickup display and fulfillment selection are deferred to Feature 13.

**Authorization/security:** Every pickup settings read and write verifies the authenticated owner against the market ID before accessing the address. Other owners receive 404 and anonymous requests receive 401. The request cannot provide a market owner or market address relationship independently. Pickup settings do not alter buyer addresses, shipping, checkout, cart, orders, or Timbre purchase authorization.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused market, buyer, owner, product, and address run passes all 118 tests, including atomic save-and-enable, disabled address retention, disable-before-removal, invalid configuration preservation, owner isolation, anonymous rejection, Feature 2 migration, and direct database invariant enforcement. The complete suite reports 310 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Pickup settings are API-only. No buyer-facing pickup address, pickup selection, operating hours, inventory reservation, order creation, or checkout integration exists yet.

### Feature 12: Market Shipping Settings

**Status:** Implemented on 2026-09-26.

**Changes:** Market owners can save supported shipping methods and enable shipping only when at least one method exists. The supported canonical methods are `USPS`, `UPS`, `FEDEX`, and `LOCAL_DRIVER`; markets may choose any nonempty subset. Owners can save methods while shipping is disabled, enable later, replace the active method set safely, disable shipping, and clear methods once shipping is disabled.

**Files modified:** `api/db.py`, `api/markets.py`, `tests/test_markets.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added persisted `markets.shipping_enabled`, a `market_shipping_methods` relationship with a canonical-method constraint and unique market-method key, plus an additive migration for existing market databases. Database triggers reject enabling shipping without a method, creating a market with shipping already enabled, and removing the final method while shipping is enabled.

**Routes:** Added owner-only `GET /markets/{market_id}/shipping-settings` and `PATCH /markets/{market_id}/shipping-settings`. PATCH accepts `shippingEnabled` and/or `supportedShippingMethods`, rejects duplicate or unsupported methods and an enabled empty set, and returns the canonical configured methods. It stores and displays carrier choices only. It does not call carrier APIs or fabricate tracking updates.

**Authorization/security:** Every shipping settings request validates current market ownership before reading or writing configuration. Anonymous callers receive 401 and another owner receives 404. Client requests cannot select a different market. Shipping settings do not change pickup, buyer addresses, cart, checkout, orders, inventory, payment, or Timbre purchase authorization.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. The focused market, buyer, owner, product, and address run passes all 128 tests, including method configuration, enabling, replacement, disabling and clearing, duplicate and unsupported-method rejection, owner isolation, anonymous rejection, direct database invariant enforcement, and the prior pickup migration behavior. The complete suite reports 320 passed and the same 2 process-order-dependent SIGABRT failures in pre-existing fresh-interpreter issuer guards on this macOS runtime; all 7 guards pass in isolation. The 67-module frontend build, Python compilation, and `git diff --check` pass.

**Known limitations:** Shipping settings are API-only. Feature 13 exposes valid configured pickup or shipping choices to a buyer, but carrier rate lookup, label purchase, tracking, checkout integration, and order creation are not implemented.

### Feature 13: Checkout Fulfillment Selection

**Status:** Implemented on 2026-09-26.

**Changes:** Added a buyer-authenticated fulfillment-selection API for a specific market. It returns only shipping and pickup methods that the market has actually enabled, requires a saved address for shipping, shows the active pickup address for pickup, and persists one current selection for each buyer-market pair. Re-selecting a method replaces that buyer's prior selection for the same market.

**Files added:** `api/fulfillment_selection.py`, `tests/test_fulfillment_selection.py`.

**Files modified:** `api/db.py`, `api/main.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added `buyer_market_fulfillment_selections`, keyed by buyer account and market. It stores either `SHIP` with a buyer-owned shipping address or `PICKUP` with no shipping address. Check constraints enforce that shape, and database triggers reject non-buyer accounts and cross-buyer address references even outside the API.

**Routes:** Added buyer-authenticated `GET /buyer/markets/{market_id}/fulfillment-options` and `PUT /buyer/markets/{market_id}/fulfillment-selection`. The options response lists shipping only when the market has shipping enabled and configured methods, and lists pickup only when pickup is enabled and a pickup address exists. PUT returns 409 for an unavailable fulfillment method and 422 for a missing, unknown, or another buyer's shipping address. `PUT` was added to the existing origin-restricted credentialed CORS methods.

**Authorization/security:** The authenticated buyer is derived only from the session. The server validates every selected market's current fulfillment configuration, verifies the supplied shipping address belongs to that buyer, and never accepts a client-provided buyer ID. A buyer cannot write another buyer's selection or use another buyer's private address. This selection changes neither payment nor existing Timbre purchase authorization.

**Checkout boundary:** The existing `api/checkout.py` remains untouched because it prices the separate seeded legacy catalog and has no market identifier. The selection API is a validated staging point for Feature 14 order creation, not an order or payment action. A destructive checkout rewrite was avoided; Feature 14 must consume the selection only after it has a market-aware order/cart mapping.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. Python compilation, `git diff --check`, and the focused buyer, market, address, authentication, and fulfillment suite pass with 134 tests. The isolated issuer guard suite passes all 7 tests. The production frontend build passes with 67 modules. The complete suite reports 326 passed and the same 2 pre-existing process-order-dependent SIGABRT failures in fresh-interpreter issuer import guards on this macOS runtime; those two guards pass in their isolated file.

**Known limitations:** There is no buyer fulfillment UI, carrier rates, labels, inventory reservation, or change to the legacy seeded-catalog checkout. Feature 14 now consumes the saved selection through a separate market-aware checkout confirmation route.

### Feature 14: Order Creation

**Status:** Implemented on 2026-09-26.

**Changes:** Added an isolated market-aware checkout confirmation route for one market's products. It re-prices seller products on the server, snapshots product names, prices, requested amounts, unit data, and the previously selected shipping or pickup details, then starts the existing issuer authorization flow. A persistent market order is created only after that issuer flow returns a verified transaction. The order begins in `NOT_STARTED` status.

**Files added:** `api/market_orders.py`, `tests/test_market_orders.py`.

**Files modified:** `api/db.py`, `api/main.py`, `api/checkout.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added short-lived `market_checkout_sessions` that snapshot a buyer's proposed market purchase before authorization. Added immutable-after-creation `market_orders` and `market_order_items`, which preserve the product name, integer-cent price, purchased amount, product measurement, fulfillment method, and applicable shipping or pickup address at purchase time. Market orders have a unique issuer instruction, buyer and market relationships, paid transaction identifier, timestamps, and initial `NOT_STARTED` fulfillment status.

**Routes:** Added buyer-authenticated `POST /buyer/markets/{market_id}/checkout/confirm`. It rejects an unknown market, duplicate items, another market's products, missing fulfillment selection, unavailable or missing fulfillment address, and invalid quantities. It returns the issuer `instructionId` and `sessionId` for the existing Timbre authorization UI. Existing `POST /checkout/complete` now recognizes either legacy or market checkout instructions and materializes a market order after verification, while preserving its exact two-field public response.

**Pricing and authorization:** Product prices always come from the current server-side `market_products` row at confirmation and are then frozen in the session and order snapshots. The current total equals the product subtotal because Features 12 and 14 have no carrier-rate or market shipping-fee calculation. A market checkout cannot create an order, status change, payment authorization, or successful result on its own. It uses the existing issuer session and only a verified issuer response writes `market_orders`.

**Preservation decision:** The existing legacy checkout route and its seeded catalog are preserved. The new market-aware route is additive because the legacy cart has no market identifiers. The legacy response contract remains exactly `{verified, transaction_id}`.

**Verification:** Reinstalled all pinned requirements and ran `pip check`; no dependency was added. Python compilation and the focused market order, fulfillment, market, buyer, product, and issuer-boundary suite pass with 156 tests. The focused tests cover verified creation, unverified non-creation, product and fulfillment snapshots, buyer authentication, missing selection, and cross-market product rejection. The isolated issuer guard suite passes all 7 tests. The production frontend build passes with 67 modules. The complete suite reports 329 passed and the same 2 pre-existing process-order-dependent SIGABRT failures in fresh-interpreter issuer import guards on this macOS runtime; those two guards pass in their isolated file. `git diff --check` passes.

**Known limitations:** No buyer order history or details endpoint exists yet, and no market dashboard can read these orders until Features 16 and 20. Shipping totals are product subtotal only until carrier or market shipping fees are modeled. Inventory is not reserved or decremented. Feature 15 now splits a market-aware cart into private market orders.

### Feature 15: Multi-Market Order Splitting

**Status:** Implemented on 2026-09-26.

**Changes:** Added buyer-authenticated `POST /buyer/markets/checkout/confirm` for market-tagged cart lines. It groups lines by market, verifies each market's fulfillment selection and product ownership, uses one existing issuer authorization session for the combined total, and creates separate internal market orders after authorization succeeds.

**Files modified:** `api/db.py`, `api/market_orders.py`, `api/checkout.py`, `tests/test_market_orders.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added `authorization_instruction_id` to checkout snapshots. A multi-market checkout uses a distinct internal snapshot ID for each market and one shared authorization instruction. Existing Feature 14 snapshots are migrated to use their original instruction as the authorization instruction.

**Authorization/security:** Each internal order retains its own market ID, product snapshots, fulfillment snapshot, and transaction ID. The market checkout route never accepts a client total or a market ID detached from its products. The existing two-field completion response and issuer authorization boundary remain unchanged.

**Verification:** `tests/test_market_orders.py` passes all 4 tests, including one issuer-approved checkout containing two markets that produces two distinct market orders with one transaction ID. `git diff --check` passes. No dependency was added.

**Known limitations:** Feature 16 now provides a market order dashboard API. Buyer order UI, shipping cost, inventory reservation, and carrier features remain unimplemented. The legacy seeded-catalog cart is unchanged because it has no market IDs.

### Feature 16: Market Order Dashboard

**Status:** Implemented on 2026-09-26.

**Changes:** Added owner-only `GET /markets/{market_id}/orders`. It returns a market's completed authorized orders with ordered item snapshots, totals, fulfillment type, applicable shipping or pickup data, current status, and timestamps.

**Files modified:** `api/market_orders.py`, `api/main.py`, `tests/test_market_order_dashboard.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Authorization/security:** The route verifies the market ID and owner account in one server-side query. Another owner receives 404 and cannot read a different market's orders. Responses omit buyer account IDs, email addresses, payment data, and transaction IDs.

**Verification:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py tests/test_market_orders.py -q` passes 5 tests. `git diff --check` passes. No dependency was added.

**Known limitations:** This is an API dashboard only. Order status changes, tracking, buyer order history, and carrier operations are deferred.

**Follow-on:** Feature 17 adds the owner status workflow below.

### Feature 17: Order Status Workflow

**Status:** Implemented on 2026-09-26.

**Changes:** Added owner-only `PATCH /markets/{market_id}/orders/{order_id}/status` with the server-enforced transitions `NOT_STARTED` to `FULFILLING` to `ORDER_COMPLETE`, then `SHIPPING` for shipping orders or `READY_FOR_PICKUP` for pickup orders. Invalid skips, reversals, and fulfillment-mismatched terminal states return 422.

**Files modified:** `api/db.py`, `api/market_orders.py`, `tests/test_market_order_dashboard.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Database/schema:** Added an additive `fulfillment_status` column because the existing Feature 14 `status` column was intentionally constrained to `NOT_STARTED`. This preserves all existing records and avoids a destructive SQLite table rebuild. The original status remains the paid-order creation marker; fulfillment status is the mutable state machine field.

**Authorization/security:** The mutation verifies both market ownership and the order's market relationship in one server-side query. Another owner cannot update the order. No client-provided status can bypass the allowed transition graph.

**Verification:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` passes 2 tests, including invalid terminal state rejection and the complete pickup workflow. `git diff --check` passes. No dependency was added.

**Known limitations:** Dashboard and workflow are API-only. Carrier tracking, local driver state, buyer status view, and notifications remain deferred.

**Next feature:** Feature 18, carrier tracking. Do not begin it until explicitly continuing the required feature cycle.

### Feature 18: Carrier Tracking

**Status:** Implemented on 2026-09-26.

**Changes:** Added owner-only `PATCH /markets/{market_id}/orders/{order_id}/tracking`. Shipping orders can store one USPS, UPS, or FedEx carrier and tracking number. The existing market dashboard returns both fields.

**Files modified:** `api/db.py`, `api/market_orders.py`, `tests/test_market_order_dashboard.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Authorization/security:** Tracking updates verify the market owner and order-market relationship server-side. Pickup orders reject tracking. Only validated carrier values are accepted. This stores merchant-provided tracking information and does not fabricate carrier events.

**Verification:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` passes 3 tests. `git diff --check` passes. No dependency was added.

**Known limitations:** No carrier API, delivery-event polling, buyer tracking view, or local-driver workflow exists yet.

**Next feature:** Feature 19, local-driver shipping. Do not begin it until explicitly continuing the required feature cycle.

### Feature 19: Local Driver Shipping

**Status:** Implemented on 2026-09-26.

**Changes:** Added owner-only `PATCH /markets/{market_id}/orders/{order_id}/local-driver` for shipping orders. It marks an order as local-driver delivery, clears any carrier tracking data, and exposes `localDriver` plus the buyer-facing message, "A local driver is handling this delivery," in the market dashboard response.

**Files modified:** `api/db.py`, `api/market_orders.py`, `tests/test_market_order_dashboard.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Authorization/security:** The action verifies owner and market relationship server-side and rejects pickup orders. Local-driver delivery does not accept or fabricate USPS, UPS, or FedEx tracking numbers.

**Verification:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` passes 4 tests. `git diff --check` passes. No dependency was added.

**Known limitations:** No live driver assignment, GPS, delivery notifications, or buyer order-details screen exists yet.

**Next feature:** Feature 20, buyer order history. Do not begin it until explicitly continuing the required feature cycle.

### Feature 20: Buyer Order History

**Status:** Implemented on 2026-09-26.

**Changes:** Added buyer-authenticated `GET /buyer/markets/orders`. It lists the current buyer's market orders, including market name, purchased item snapshots, total, purchase time, fulfillment method, and current fulfillment status.

**Files modified:** `api/market_orders.py`, `tests/test_market_order_dashboard.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Authorization/security:** The query scopes orders by the authenticated buyer account. Another buyer receives an empty history and cannot obtain another buyer's orders, shipping address, transaction ID, or tracking information from this endpoint.

**Verification:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` passes 5 tests. `git diff --check` passes. No dependency was added.

**Known limitations:** This is API-only order history. Buyer order details, shipment tracking, pickup information, and local-driver messaging are deferred to Feature 21.

**Next feature:** Feature 21, buyer order details and status. Do not begin it until explicitly continuing the required feature cycle.

### Feature 21: Buyer Order Details and Status

**Status:** Implemented on 2026-09-26.

**Changes:** Added buyer-authenticated `GET /buyer/markets/orders/{order_id}`. It returns an individual order's market, purchased items, amount paid, current status, fulfillment type, shipping or pickup address when applicable, carrier tracking, and local-driver message when applicable.

**Files modified:** `api/market_orders.py`, `tests/test_market_order_dashboard.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Authorization/security:** The order query matches both order ID and authenticated buyer account. Another buyer receives 404. The endpoint exposes only the buyer's own fulfillment data and does not expose market-owner account or payment-authorization internals.

**Verification:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` passes 6 tests. `git diff --check` passes. No dependency was added.

**Known limitations:** Buyer history and details are API-only. There are no buyer UI screens, notification delivery, carrier polling, or live local-driver tracking.

**Next feature:** Feature 22, commerce-agent multi-market integration. Do not begin it until explicitly continuing the required feature cycle.

### Feature 22: Commerce-Agent Multi-Market Integration

**Status:** Implemented, read-only marketplace search on 2026-09-26.

**Changes:** Added `GET /agentic-shopping/commerce/marketplace-products?query=...`, a read-only catalog adapter that searches live products across markets and returns each product's market, price, display quantity, compatible normalized quantity, and quantity-per-dollar values. It only returns direct seller data and does not invent markets, products, or inventory.

**Files added:** `api/marketplace_catalog.py`, `tests/test_marketplace_catalog.py`.

**Files modified:** `api/main.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Comparison safety:** Responses retain the seller display unit and include normalized values and dimensions from Feature 8. Weight, volume, and count remain distinct, so a consumer can compare quantity-per-dollar only within a compatible dimension.

**Preservation decision:** The existing agentic browser cart accepts only legacy catalog IDs, while market checkout uses market-tagged product IDs. Replacing that working cart would be destructive, so this feature exposes marketplace search data and keeps market checkout through the Feature 15 route. A future adapter can add the market-tagged selection to the browser cart without modifying seller inventory, fulfillment, authorization, or payment behavior.

**Verification:** `.venv/bin/python -m pytest tests/test_marketplace_catalog.py -q` passes 1 test. `git diff --check` passes. No dependency was added.

**Known limitations:** Marketplace results are API-only and are not yet rendered by the agentic UI or directly added to the legacy browser cart. The marketplace search cannot modify products, order status, fulfillment choices, or payment authorization.

**Boardwalk shops (2026-09-26, 343 tests pass):** the storefront is four themed shops on one merchant (Seaside Grocer, Seaside Tech, Sandbar Sun & Care, Landlubber Pets; 88 real products with photos from the Open Food Facts projects). One cart, one checkout, one issuer session, so the §2.5 boundary is unchanged. Agentic shopping and voice search cover every shop, and naming a shop limits the search to it. Details in the 16:30 CHANGELOG entry.

**Next, in order:**
0. Set a valid backend `OPENAI_API_KEY` and speak a catalog request through the new full-request panel to verify the live provider round trip. Automated provider behavior is covered with mocked responses, but no live key was available during implementation.
1. Phase 7 live: set `LLM_API_KEY` and try a spoken item end to end. The rerank on-vs-off intent-accuracy delta (§3.2) needs real recordings of people naming catalog items; TORGO has none and §2.3 forbids imitating them.
2. Decide whether adaptation needs a cumulative drift cap: per-update `MAX_DRIFT` holds, but templates drifted 0.18 to 0.32 over many updates in `make drift` (impostor accept 1.46% -> 1.96%).
3. Spoken confirmation (§10.3) and dispute drafting (§10.4) are not built.
3a. Accuracy: cheap candidates rejected (ADR 7); encoders not adopted (ADR 8); fusion failed a pre-registered test on EasyCall (ADR 9), while the live design held (dysarthric EER 2.43%, 2.84% vs same-word attackers). Quote only with ADR 9's caveats.
4. Phase 10: demo hardening, `docs/DEMO.md`, VIC mapping in ADR 1, README/Devpost (check `docs/CONTEXT.md` §11 before claiming anything).

**Open decisions for the person:** (a) decided 2026-09-26: after 2 failed voice attempts any purchase completes with the passkey alone (ADR 5), and a voice match approves any amount with no passkey step-up (ADR 12, removed the $50 tier); (b) roll the Stripe test key after the event (it was shared in chat).

**Verified by a human (2026-09-26, afternoon, tag `working-demo-2026-09-26` at 5531435):** the full flow after ADR 12, including agentic voice and typed shopping, voice approval, passkey fallback, and a Stripe receipt. Voice approval accepted the enrolled owner and rejected a second person trying the same card (one live trial, not a measured rate; see ADR 9). Before that, also 2026-09-26: a real fingerprint passkey registration and a full UI purchase through Stripe (passkey-only, merchant saw only `{verified, transaction_id}`). Caveat: in Edge, a passkey saved to Microsoft Password Manager failed to sign when Windows routed it through its passkey-provider path (fingerprint passed, then "There was a problem signing in with your passkey"); re-registering fixed it. On the demo machine, rehearse the passkey step once, and if it fails check `Get-WinEvent -LogName Microsoft-Windows-WebAuthN/Operational` for `PluginGetAssertionRequest`.

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
CYBERSOURCE_MERCHANT_ID=         # PAYMENT_PROVIDER=visa (ADR 13): CyberSource sandbox
CYBERSOURCE_KEY_ID=
CYBERSOURCE_SECRET_KEY=
CYBERSOURCE_CUSTOMER_MAYA=       # customer token IDs from the Business Center, never card numbers
CYBERSOURCE_CUSTOMER_JORDAN=
LLM_PROVIDER=anthropic           # anthropic | gemini
LLM_API_KEY=
OPENAI_API_KEY=                  # agentic shopping only; server-side
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

## Marketplace Frontend Implementation Progress

### Frontend Feature 1: User Icon and Account Menu

**Status:** Implemented on 2026-09-26.

**Changes:** Added an accessible profile icon and account menu to the existing storefront header. It retains the existing storefront, voice-shopping launcher, and cart controls. The menu shows buyer links when a buyer session exists and shows Market Dashboard only when a separate market-owner session exists. Logout clears either active server-side session and leaves the cart intact.

**Files modified:** `web/src/components/SiteHeader.jsx`, `web/src/components/Icons.jsx`, `web/src/lib/api.js`, `web/src/styles.css`, `AGENTS.md`, `docs/CHANGELOG.md`.

**APIs used:** `GET /buyer-auth/me`, `GET /market-auth/me`, `POST /buyer-auth/logout`, and `POST /market-auth/logout`. The shared frontend request helper now includes credentials, which is required for the existing HttpOnly session cookies; it handles the logout endpoints' 204 responses.

**Verification:** `npm --prefix web run build` passes with 68 modules. `git diff --check` passes.

**Known limitations:** Buyer Dashboard, Orders, Addresses, Account Settings, and Market Dashboard destinations are menu links only until their respective frontend features are implemented. There is no login UI yet, so session creation remains through the existing account APIs.

**Next frontend feature:** Feature 2, fast market switcher. Do not begin it until explicitly continuing the required feature cycle.

### Frontend Feature 2: Fast Market Switcher

**Status:** Implemented on 2026-09-26.

**Changes:** Made the current market name in the storefront header a searchable modal switcher. `App` owns `selectedMarketId`, persists it for the viewer, and passes it to both the header and Shop page. Selecting a market updates the header and the displayed market sections without a page reload. The existing shared cart remains untouched.

**Files modified:** `web/src/App.jsx`, `web/src/components/SiteHeader.jsx`, `web/src/pages/Shop.jsx`, `web/src/styles.css`, `AGENTS.md`, `docs/CHANGELOG.md`.

**APIs used:** Existing `GET /store` market metadata and existing `GET /catalog` boardwalk catalog through the shared store-information and catalog hooks.

**Verification:** `npm --prefix web run build` passes with 68 modules. `git diff --check` passes.

**Known limitations:** The legacy boardwalk backend serves the catalog as one read-only payload and its existing product records use a `market` label, so switching filters the already loaded catalog instead of requesting a per-market catalog. This preserves the current cart and checkout behavior. A future backend adapter should provide a market-scoped catalog endpoint before the client changes to per-market fetches; no destructive catalog or cart rewrite was made.

**Next frontend feature:** Feature 3, buyer dashboard. Do not begin it until explicitly continuing the required feature cycle.

## Database-Backed Storefront Migration

### Feature 1: Seed Seaside Grocer as a Persisted Marketplace

**Status:** Backend foundation implemented on 2026-09-26. Frontend migration remains incomplete.

**Changes:** Added database-backed `description` to markets and `brand` plus `category` to market products. Added public storefront reads at `GET /storefront/markets` and `GET /storefront/markets/{market_id}/products`, which return persisted branding, market description, product records, category values, photos, measurements, and normalized quantity data. `scripts/seed_demo.py` now creates a system-owned Seaside Grocer record and exactly 18 requested product records with persisted category, price, quantity, unit, and existing legacy image references when available.

**Files added:** `api/storefront.py`.

**Files modified:** `api/db.py`, `api/main.py`, `scripts/seed_demo.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `.venv/bin/python -m scripts.seed_demo` seeds 88 legacy catalog rows and 18 persisted Seaside Grocer marketplace products. Direct TestClient checks return Seaside Grocer, its persisted description, 18 products, and seven categories through the public storefront API. Python compilation, `npm --prefix web run build` (68 modules), and `git diff --check` pass.

**Known limitation and required next work:** The browser storefront still reads the legacy `products` catalog because its shared cart and checkout price legacy product IDs. Redirecting it to the new marketplace records without an additive product-ID/cart adapter would break checkout. No destructive replacement was made. The next task must add that adapter and switch the frontend atomically to the new storefront endpoints, including data-driven category rendering and market search, before any buyer-dashboard work.

### Feature 1 Repair: Database-Backed Browser Storefront

**Status:** Implemented on 2026-09-26.

**Changes:** Replaced the browser storefront's `GET /catalog` dependency with `GET /storefront/markets` and `GET /storefront/markets/{market_id}/products`. The selected-market request returns the persisted market and its products only. The application retains previously fetched product records only as a cart display cache, so switching markets does not clear existing cart lines. Storefront category groups now derive directly from product category values rather than the old shop-category mapping.

**Files modified:** `api/cart.py`, `web/src/App.jsx`, `web/src/pages/Shop.jsx`, `web/src/lib/api.js`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Cart and checkout compatibility:** Server cart pricing now resolves an unknown legacy catalog ID against `market_products`, so the existing cart, quote, checkout, and issuer authorization path can price database-backed storefront products. Legacy catalog data remains available for historical flows while it is retired incrementally.

**Verification:** `.venv/bin/python -m scripts.seed_demo` creates Seaside Grocer and 18 products. Public storefront endpoints return only persisted market/product records. `.venv/bin/python -m pytest tests/test_boundary.py tests/test_market_products.py -q` passes 93 tests. `npm --prefix web run build` passes with 68 modules. `git diff --check` passes.

**Known limitations:** The header market switcher now uses real persisted markets, but visual market-specific logos/themes and the cart's legacy shop-name labels still need their own data-driven adapter. The footer copy still describes the former boardwalk demo. No fallback catalog is used on a storefront API error.

**Next required repair:** Make market branding and the header switcher commit atomically from one persisted selected-market response, then continue frontend features.

### Feature 2 Repair: Atomic Persisted Market Switching

**Status:** Implemented on 2026-09-26.

**Changes:** The visible selected market now remains unchanged until `GET /storefront/markets/{market_id}/products` returns the requested persisted market and its catalog. The completed response updates the header identity and Shop inventory together. The header uses the persisted market name, optional logo, description, and primary-color value. Storefront product records now include their persisted market name, allowing the existing cart drawer and checkout to label marketplace cart lines without reading the retired boardwalk market metadata endpoint.

**Files modified:** `api/storefront.py`, `web/src/App.jsx`, `web/src/components/SiteHeader.jsx`, `web/src/components/CartDrawer.jsx`, `web/src/pages/Checkout.jsx`, `web/src/pages/Shop.jsx`, `web/src/styles.css`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `.venv/bin/python -m pytest tests/test_boundary.py tests/test_market_products.py -q` passes 93 tests. `npm --prefix web run build` passes with 67 modules. `git diff --check` passes.

**Known limitations:** The legacy boardwalk catalog remains server-side for the preserved legacy voice-shopping path and existing historical flows. It is not a browser storefront fallback. The global footer still has old boardwalk demo copy and should be made neutral in a later copy-only repair.

**Next required repair:** Replace remaining legacy runtime market metadata used by server-side shopping intent with database-backed market discovery, preserving the Whisper path and existing shopping behavior.

### Frontend Feature 3: Buyer Dashboard

**Status:** Implemented on 2026-09-26.

**Changes:** Added the Buyer Dashboard at `#/buyer-dashboard`, linked from the existing authenticated buyer menu. It reads only `GET /buyer/markets/orders` and deterministically calculates 30-day spending, orders this month, active fulfillment count, and the most visited market from the authenticated buyer’s persisted orders. It also shows up to five recent orders and accurate loading, error, and no-history states.

**Files added:** `web/src/pages/BuyerDashboard.jsx`.

**Files modified:** `web/src/App.jsx`, `web/src/lib/api.js`, `web/src/lib/router.js`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `npm --prefix web run build` passes with 68 modules. `git diff --check` passes.

**Known limitations:** The dashboard intentionally has no fabricated insight or chart data. The detailed Orders page, Buy Again, and buyer AI insights remain later frontend features.

**Next frontend feature:** Feature 4, Buyer Orders and Order Details.

### Frontend Feature 4: Buyer Orders and Details

**Status:** Implemented on 2026-09-26.

**Changes:** Added `#/buyer-orders` with All, Active, Shipping, and Pickup filters, plus authenticated detail routes at `#/buyer-orders/{orderId}`. The UI uses existing persisted buyer-order records for purchased items, prices, totals, status, fulfillment type, shipping or pickup location, carrier tracking, and local-driver delivery. Progress labels reflect the backend status, and no order state is mutated by the buyer UI.

**Files added:** `web/src/pages/BuyerOrders.jsx`.

**Files modified:** `web/src/App.jsx`, `web/src/lib/api.js`, `web/src/lib/router.js`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `npm --prefix web run build` passes with 69 modules. `git diff --check` passes.

**Known limitations:** There is no Buy Again action yet. Filtered orders are loaded from the existing history endpoint and current backend statuses do not include a separate completed terminal state.

**Next frontend feature:** Feature 5, Buy Again.

### Frontend Feature 5: Buy Again

**Status:** Implemented on 2026-09-26.

**Changes:** Added an authenticated `POST /buyer/markets/orders/{orderId}/buy-again` resolver. It verifies the order belongs to the active buyer, resolves its item snapshots against current products in the original market, returns only available lines with current-price changes, and never writes cart, checkout, payment, or order state. The order-detail Buy Again control applies available quantities to the existing browser cart and reports unavailable and price-changed items.

**Files modified:** `api/market_orders.py`, `web/src/lib/api.js`, `web/src/pages/BuyerOrders.jsx`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `.venv/bin/python -m pytest tests/test_market_orders.py -q` passes 4 tests. The frontend build remains pending because Vite needs permission to write its temporary config file in `web/node_modules/.vite-temp`.

**Known limitations:** Product availability is represented by the product’s continued presence in the market catalog. There is no inventory-count model yet.

**Next frontend feature:** Feature 6, Buyer AI Insights.

### Frontend Feature 6: Buyer Insights

**Status:** Implemented on 2026-09-26.

**Changes:** Added buyer-authorized shopping insights to the existing dashboard. The client deterministically derives the most visited market, most purchased item, and most common fulfillment method from the authenticated buyer’s order history. It shows no insight section until there is enough real history.

**Files modified:** `web/src/pages/BuyerDashboard.jsx`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** Source review confirms calculations operate only on `GET /buyer/markets/orders` results. A frontend build remains pending temporary-directory write permission.

**Known limitations:** These are deterministic explanations, not an OpenAI summary, so they do not add an API-key or data-sharing path.

**Next frontend feature:** Feature 7, Market Owner Shell.

### Frontend Feature 7: Market Owner Shell

**Status:** Implemented on 2026-09-26.

**Changes:** Added the protected `#/market-dashboard` operator shell. It verifies the existing market-owner session before showing a distinct market-management navigation for Overview, Orders, Products, Analytics, Storefront, Fulfillment, and Account. Anonymous visitors receive an access message and no market data.

**Files added:** `web/src/pages/MarketDashboard.jsx`.

**Files modified:** `web/src/App.jsx`, `web/src/lib/router.js`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Known limitations:** This is navigation only. Individual market operator pages are later features and are not represented with sample data.

**Next frontend feature:** Feature 8, Market Overview and Kanban.

### Market Owner Discovery Adapter

**Status:** Implemented on 2026-09-26.

**Changes:** Added authenticated `GET /markets/mine`, returning only database market records whose `owner_account_id` matches the active market-owner session. This provides the market selector data required for the real order board without hardcoded market IDs.

**Files modified:** `api/markets.py`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Security:** Ownership is enforced in the query. Anonymous requests and buyers remain rejected through the existing `MarketOwner` dependency.

### Frontend Feature 8: Market Overview Kanban

**Status:** Implemented on 2026-09-26.

**Changes:** The protected market dashboard now discovers the owner’s persisted markets and loads orders only for the first owned market through the existing owner-scoped order API. It renders real order cards in Not Started, Fulfilling, Order Complete, Shipping, and Ready for Pickup columns, with accurate empty, loading, and error states.

**Files modified:** `web/src/lib/api.js`, `web/src/pages/MarketDashboard.jsx`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Known limitations:** Market selection and order-status controls are later features. No fake orders are displayed.

**Next frontend feature:** Feature 9, Market Orders.

### Storefront Authentication Repair

**Status:** Implemented on 2026-09-26.

**Changes:** Added public `GET /buyer-auth/session` and `GET /market-auth/session` probes that return `{account: null}` for anonymous visitors. The storefront header now uses these probes instead of protected `/me` endpoints, so anonymous shopping no longer produces 401 responses. Protected dashboards and existing `/me` routes still require their respective authenticated sessions. Checkout was not changed and remains available without a buyer or market login.

**Files modified:** `api/buyer_auth.py`, `api/market_auth.py`, `web/src/components/SiteHeader.jsx`, `web/src/lib/api.js`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `git diff --check` passes. Python bytecode compilation could not write its cache file under the restricted environment; no application code error was reported.

### Storefront Catalog Reload Repair

**Status:** Implemented on 2026-09-26.

**Changes:** Restored `catalog.reload(marketId)` as a promise-returning asynchronous operation. It now resolves after the requested persisted market catalog is committed to state and rejects after recording an error. Initial loading and market switching handle failures without committing the requested market ID, so the previously valid market identity and data remain together.

**Files modified:** `web/src/App.jsx`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `npm --prefix web run build` passes with 69 modules. `git diff --check` passes.

### Storefront Product-Market Relationship Repair

**Status:** Implemented on 2026-09-26.

**Changes:** Replaced the stale `shopOf` reference in `Shop.jsx` with the persisted `product.market` relationship returned by the database storefront endpoint. Category groups and counts continue to derive from the selected market’s fetched products only.

**Files modified:** `web/src/pages/Shop.jsx`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `npm --prefix web run build` passes with 69 modules. `git diff --check` passes. A source search confirms no `shopOf` reference remains in `Shop.jsx`.

### Shop Banner Contrast Repair

**Status:** Implemented on 2026-09-26.

**Changes:** Applied the existing dark green `--band` color directly to `.shop-banner-body` with white text, ensuring a reliable high-contrast banner even when a database market ID has no legacy CSS shop-color mapping.

**Files modified:** `web/src/styles.css`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Follow-up:** Applied the same dark green backdrop to the banner awning, replacing its legacy shop-color stripe dependency.

### Copy Repair: Remove Stale Boardwalk Branding

**Status:** Implemented on 2026-09-26.

**Changes:** Browser document titles now derive from the database-selected market on storefront, checkout, and receipt routes. Replaced the old footer sentence that named Seaside Market and four boardwalk shops with neutral application copy.

**Files modified:** `web/src/App.jsx`, `AGENTS.md`, `docs/CHANGELOG.md`.

**Verification:** `npm --prefix web run build` passes with 67 modules. `git diff --check` passes.

**Known limitations:** This is presentation-only. Legacy server-side catalog metadata still needs a database-backed adapter for the preserved legacy shopping paths.

**Next required repair:** Replace remaining legacy runtime market metadata used by server-side shopping intent with database-backed market discovery, preserving the Whisper path and existing shopping behavior.


### Continuation checkpoint: Repair authoritative storefront shopping context

**Status:** Implemented and verified on 2026-09-26. This entry supersedes conflicting historical limitations above.

Files: api/catalog.py, api/shopping.py, api/agentic_shopping.py, api/openai_intent.py, api/commerce_agent.py, api/storefront.py, scripts/seed_demo.py, web/src/App.jsx, web/src/lib/api.js, web/src/pages/Shop.jsx, web/src/components/VoiceShopping.jsx, web/src/components/AgenticVoiceShopping.jsx, tests/conftest.py, tests/test_shopping.py, tests/test_storefront_scope.py. Runtime market metadata and shopping catalog now come from persisted markets and products. Every active browser shopping stage carries its selected market; switching cancels old sessions. Failed switches retain the valid storefront, empty markets remain selectable, and retry supplies a real market ID. Legacy stored cart product IDs remain priceable for compatibility; no runtime demo market array remains. Initial checkpoint build and 24 order/auth tests passed. Feature 8 still needs its error-path repair before forward progress.

**Verification:** 53 selected-market, Whisper, agentic intent, basket and commerce tests pass; frontend production build passes.


### Continuation checkpoint: Repair Buy Again and restored cart metadata

**Status:** Implemented and verified on 2026-09-26. This entry supersedes conflicting historical limitations above.

Files: api/storefront.py, web/src/lib/api.js, web/src/App.jsx, web/src/pages/BuyerDashboard.jsx, tests/test_market_orders.py. The existing cart now resolves current backend product metadata across markets after restoration or Buy Again. Reordering remains additive and never creates checkout or payment. Deleted products are skipped and price changes reported. Corrected the buyer rolling-period label. Also normalized shopping import placement found in review.

**Verification:** 5 market-order tests including reorder price/deletion/isolation coverage pass; 32 boundary/storefront/order tests pass; production build passes.


### Continuation checkpoint: Repair Feature 8 Kanban load failures

**Status:** Implemented and verified on 2026-09-26. This entry supersedes conflicting historical limitations above.

Files: web/src/pages/MarketDashboard.jsx. Both market discovery and order-fetch failures now enter an error state, and unmounted requests cannot overwrite the board. The prior promise rejection handler did not catch failures inside its async success callback. This completes the earlier basic read-only board checkpoint; Feature 9 details and transitions are next.

**Verification:** Production build passes; owner order API and authentication were verified by the 24-test checkpoint run; reviewed asynchronous rejection and cancellation paths.


### Continuation checkpoint: Feature 9 Market Order Board

**Status:** Implemented and verified on 2026-09-26. This entry supersedes conflicting historical limitations above.

Files: api/market_orders.py, web/src/pages/MarketDashboard.jsx, web/src/pages/MarketOrderDetails.jsx, web/src/lib/marketOrders.js, web/src/lib/api.js, web/src/lib/router.js, web/src/App.jsx, web/src/styles.css. Extended the existing board with owned-market selection, backend-provided allowed transitions, status buttons, order-detail links, quantities and order age. Detail view shows persisted items and fulfillment snapshots. Unauthorized access is a real access state; empty columns remain empty. No orders or markets were inserted for UI population. Feature numbering now follows the continuation request: Feature 10 is Orders and Attention.

**Verification:** 41 owner-dashboard/market tests pass; frontend production build passes; browser confirms anonymous dashboard access is blocked; git diff check passes.


### Continuation checkpoint: Feature 10 Market Orders and Attention

**Status:** Implemented and verified on 2026-09-26. This entry supersedes conflicting historical limitations above.

Files: api/db.py, api/market_orders.py, tests/test_market_order_dashboard.py, web/src/pages/MarketOrders.jsx, web/src/pages/MarketDashboard.jsx, web/src/pages/MarketOrderDetails.jsx, web/src/lib/marketOrders.js, web/src/lib/marketOrders.test.js, web/src/lib/router.js, web/src/App.jsx, web/src/styles.css. Orders now support all five stage filters, All, and newest/oldest/highest-value sorting. Details use stored item and address snapshots and backend transition rules. Attention labels describe stage and elapsed time without invented deadlines or historical averages. Additive status-history triggers record new orders and transitions; pre-existing advanced stages are not backfilled with invented timestamps. Tracking edits cannot reset stage age.

**Verification:** 11 order/dashboard tests pass; Node filter/sort/attention test passes; production build and git diff check pass.


### Continuation checkpoint: Feature 11 Market Analytics

**Status:** Implemented and verified on 2026-09-26. This entry supersedes conflicting historical limitations above.

Files: api/market_analytics.py, api/main.py, tests/test_market_analytics.py, web/src/pages/MarketAnalytics.jsx, web/src/pages/MarketDashboard.jsx, web/src/lib/api.js, web/src/lib/router.js, web/src/App.jsx, web/src/styles.css. Owner-authorized analytics computes revenue, order count, average order value, top products, units and product revenue from paid order/item snapshots. Rolling UTC windows are 7, 30 and 365 days; prior-period percentages are omitted when undefined. Deleted catalog products retain historical names and prices. No chart library exists, so daily revenue is an accessible table without adding a dependency.

**Verification:** 9 analytics/dashboard tests pass including ownership, period boundaries, historical prices and empty periods; production build passes.


### Continuation checkpoint: Feature 12 Market Operational Metrics

**Status:** Implemented and verified on 2026-09-26. This entry supersedes conflicting historical limitations above.

Files: api/market_analytics.py, tests/test_market_analytics.py, web/src/pages/MarketOperations.jsx, web/src/pages/MarketDashboard.jsx, web/src/lib/api.js. Overview now shows open preparation, fulfilling, waiting-to-ship, ready-for-pickup, preparation-completed and all-time average order value metrics. Definitions explicitly distinguish preparation completion from delivery completion, which the schema does not track. Average fulfillment time includes only orders with recorded Fulfilling and Order Complete timestamps and reports its sample count; unavailable history produces an honest unavailable message.

**Verification:** 4 analytics/operations tests pass including incomplete-history exclusion and empty data; production build passes.


## Current Continuation Handoff, 2026-09-26

This is the authoritative checkpoint for the marketplace continuation. Preserve the existing storefront, issuer boundary, buyer authentication, and current dirty worktree. Do not restart the implementation or discard existing changes.

### Completed during this continuation

1. **Database-backed selected-market repair.** Runtime storefront discovery, product catalog reads, typed shopping, Whisper shopping, and agentic shopping now use the selected persisted market. The browser sends the market ID to every shopping request. A failed switch retains the previous valid market, products, and header; empty markets show an honest empty state. The legacy hardcoded runtime market array was removed from the active shopping path.
2. **Cart and Buy Again repair.** The shared cart hydrates current product metadata from the backend for all retained lines, including lines restored from session storage and Buy Again results. Buy Again only adds available current products to the existing cart, reports unavailable products and changed prices, and never creates a checkout, payment, or order.
3. **Feature 8 repair.** The existing owner Kanban now handles market discovery and order-read failures correctly and does not update after unmount.
4. **Feature 9, Market Order Board.** `#/market-dashboard` supports authenticated owned-market selection, real Kanban columns, order detail links, item counts, fulfillment method, total, order age, and backend-derived allowed transitions. The board never creates placeholder orders. Anonymous access displays the access state.
5. **Feature 10, Market Orders and Attention.** `#/market-orders/{marketId}` supports All and every fulfillment-stage filter plus newest, oldest, and highest-value sorting. Details show persisted item, shipping or pickup, carrier/tracking, local-driver, total, and current status data. Attention text describes the current stage and elapsed time only. It does not call an order late or assert a deadline. New `market_order_status_history` rows are generated at order creation and on later status transitions; old records without history show unavailable stage time.
6. **Feature 11, Market Analytics.** Owner-only `GET /markets/{marketId}/analytics?period=7D|30D|1Y` and `#/market-analytics/{marketId}` report historical revenue, order count, average order value, units, top products, product revenue, daily revenue, and mathematically valid prior-period revenue comparisons. Calculations use paid order and item snapshots, so deleted products remain in history with their purchased name and price.
7. **Feature 12, Operational Metrics.** The overview shows real open-preparation, fulfilling, waiting-to-ship, ready-for-pickup, preparation-completed, and all-time average-order-value metrics. Average fulfillment time is shown only when the order has recorded Fulfilling-to-Order Complete timestamps, with the sample count.

### Verified state

- `npm --prefix web run build` passed after Features 9 through 12, most recently with 75 transformed modules.
- `tests/test_storefront_scope.py`, `tests/test_shopping.py`, `tests/test_agentic_intent.py`, `tests/test_agentic_basket.py`, and `tests/test_commerce_agent.py` passed together: 53 tests.
- The selected market, cart, buyer reorder, boundary, and market-order focused suite passed together: 32 tests.
- `tests/test_market_order_dashboard.py` and `tests/test_market_orders.py` passed after Feature 10: 11 tests.
- `tests/test_market_analytics.py` passed after Feature 12: 4 tests.
- `node --test web/src/lib/marketOrders.test.js` passed.
- `git diff --check` passed at each checkpoint.
- Browser verification loaded `#/market-dashboard` anonymously and showed the intended market-owner access state. No test market, order, or demo business data was created to populate the UI.

### Remaining work, in order

1. **Feature 13, Market AI Insights.** This has not been implemented. Compute owner-scoped facts deterministically from persisted order, order-item, fulfillment-status, and analytics data first. If an OpenAI explanation is added, keep `OPENAI_API_KEY` server-side, set Responses API storage off, use strict structured output, and constrain the model to select or phrase supplied facts only. Do not permit invented numbers, deadlines, statuses, or elapsed times. The existing `api/openai_intent.py` demonstrates the repository's Responses API request shape and server-side key handling. Gracefully show an unavailable or no-insights state when no key or insufficient data exists.
2. **Focused shared quality pass.** Check all added marketplace pages at desktop, tablet, and mobile widths; loading, empty, and error states; visible focus behavior; compact table overflow; and sidebar/header navigation. Do not add mock values to fill empty states.
3. **Regression pass before handoff completion.** Run the combined focused suite, `npm --prefix web run build`, and `git diff --check`. Confirm storefront switching remains atomic, cart contents persist across switches, buyer dashboard/order details/Buy Again work, market data stays owner-scoped, status transitions remain backend-authorized, and no API key enters the client bundle.

### Known limitations and deliberate boundaries

- The marketplace browser cart remains compatible with the older issuer checkout route. New market-aware checkout APIs exist separately; do not silently merge or replace the purchase boundary without an explicit market-aware cart-to-checkout adapter.
- Current market selection shows the first owned market when opening a dashboard route without a market ID. Selecting another owned market changes the dashboard route; it cannot enumerate another owner’s markets.
- Carrier data is merchant-entered information only. There is no carrier polling, live driver tracking, inventory reservation, delivery completion state, or product inventory-count model.
- Analytics reports recorded paid order totals, which are revenue for this UI, not profit. The daily revenue table is intentionally used instead of adding a charting dependency.
- Feature 13 work was inspected but not started before the session interruption. No partial AI-insight implementation is expected.
