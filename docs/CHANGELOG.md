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

### 2026-09-26 14:05 - Agentic shopping by typing

- **Files:** web/src/components/AgenticVoiceShopping.jsx, docs/CHANGELOG.md.
- **What:** The agentic panel now has an "Or type the whole request" field with a Shop button under the microphone button. A typed request skips transcription and runs the same interpret, clarify, and basket steps as speech (shared `interpret` function), so questions, review, Undo, and cart-race checks behave the same. The transcript block reads "You asked for" when typed and "Timbre heard" when spoken. Heading is now "Shop a full request by voice or text". Input is capped at 1000 characters to match `AGENTIC_TEXT_MAX`, and is disabled while recording or working.
- **Why:** Lets the full agentic flow run without a microphone (demo backup, and people who prefer typing).
- **Verify:** `npm --prefix web run build`; in the browser, type "as much yogurt as I can get for ten dollars, and two cokes" and press Shop: 6 Chobani yogurts ($8.94) and 2 Coke six-packs are added with Undo; no console errors.
- **Risk/Notes:** A 503 on the typed path shows an error rather than the Whisper fallback, since there is no audio to hand over. Existing display quirk, not new: "Timbre understood" can show a brand the speaker never said (Fage here) even though commerce ignores it and picks by price.

### 2026-09-26 13:50 - Live OpenAI round trip; keep a one-item limit off the basket budget

- **Files:** api/openai_intent.py, docs/CHANGELOG.md.
- **What:** First live round trip with the real key: a synthetic (Windows TTS, typical speech) 16 kHz WAV transcribed word for word in 1.2 s, extraction takes about 3 to 4 s. It exposed a bug: "as much yogurt as I can get for ten dollars, and two Cokes" also set totalBudget 10, so the Cokes ($9.98) left $0.02 and the yogurt was dropped. The basket prompt now says a limit spoken with one product is that item's maxPrice only, with this example, and totalBudget needs words that cover everything.
- **Why:** The prompt said when to use totalBudget but not when not to, and the model copied the item limit into it.
- **Verify:** Live: that transcript now gives 6 yogurts ($8.94) plus 2 Coke six-packs; "tuna salad and two cokes, under 20 bucks" and "milk, eggs, and bread, keep it all under 15 dollars" still set totalBudget. `make test` (340 passed; prompt text is not unit-tested, provider calls are mocked).
- **Risk/Notes:** Catalog no longer has bananas or Bose (10 grocery aisles since 29aa242), so the older banana and headphone results in AGENTS.md now correctly report "not sold here". Open: a basket over its total budget is shown for removal rather than re-picked with cheaper items ($16.27 against $15 when cheaper milk exists). Not yet spoken through the browser by a person.

### 2026-09-26 13:35 - Fix shared-DB marketplace test; pin market tables to the boundary

- **Files:** tests/test_marketplace_catalog.py, tests/test_boundary.py, docs/CHANGELOG.md.
- **What:** The marketplace search test now finds its own product by id instead of assuming it ranks first (the suite shares one merchant.db, so another test's cheaper apples came back first and `make test` failed). Added `test_market_order_records_hold_no_verification_details`, which pins the columns of `market_orders` and `market_checkout_sessions` the same way `orders` is already pinned.
- **Why:** Commit 54174bc routed market checkout through `/checkout/complete`, but the §2.5 schema check covered only the original `orders` table.
- **Verify:** `make test` (340 passed). Reviewed by hand: `/checkout/complete` still returns only `ApprovalResult{verified, transaction_id}`, market orders are created only on a verified result, the market tests assert the exact two-key body, and no merchant table has a card, score, threshold, attempt, or fallback-method column.
- **Risk/Notes:** Test-only change. Timestamps on the entries below (15:10 to 15:40) are later than this entry's real clock time; they were written that way by the previous agent.

### 2026-09-26 15:40 - Add agentic marketplace catalog search

- **Files:** api/marketplace_catalog.py, tests/test_marketplace_catalog.py, api/main.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added a read-only agentic marketplace search across live market products with market identity, display and normalized quantity, and quantity-per-dollar fields.
- **Why:** The commerce agent needs real multi-market catalog data without inventing inventory or changing seller, cart, fulfillment, or payment state.
- **Verify:** `.venv/bin/python -m pytest tests/test_marketplace_catalog.py -q` (1 passed); `git diff --check`.
- **Risk/Notes:** Existing browser cart accepts legacy catalog IDs only, so marketplace results remain API-only until an additive market-tagged cart adapter is built. No dependency was added.

### 2026-09-26 15:32 - Add buyer market order details

- **Files:** api/market_orders.py, tests/test_market_order_dashboard.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added private buyer order-detail retrieval with order status, market, purchased items, fulfillment address, carrier tracking, and local-driver delivery information where applicable.
- **Why:** Buyers need to inspect the fulfillment state and details of an individual order without access to another buyer's purchases.
- **Verify:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` (6 passed); `git diff --check`.
- **Risk/Notes:** This is an API detail view only. It does not poll carriers or provide buyer notifications. No dependency was added.

### 2026-09-26 15:25 - Add buyer market order history

- **Files:** api/market_orders.py, tests/test_market_order_dashboard.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added a buyer-authenticated order history listing with market, item, total, fulfillment method, status, and date data, scoped to the current buyer.
- **Why:** Buyers need to view both active and completed orders without exposing another buyer's purchases.
- **Verify:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` (5 passed); `git diff --check`.
- **Risk/Notes:** History is API-only and does not yet provide individual order details, addresses, pickup information, or tracking. No dependency was added.

### 2026-09-26 15:17 - Add local driver delivery

- **Files:** api/db.py, api/market_orders.py, tests/test_market_order_dashboard.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added owner-authorized local-driver designation for shipping orders, clears carrier tracking when selected, and displays a local-driver delivery message in the dashboard.
- **Why:** Markets that use a local driver need a valid shipment path without requiring carrier tracking numbers.
- **Verify:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` (4 passed); `git diff --check`.
- **Risk/Notes:** This stores delivery handling only. There is no driver assignment, GPS tracking, or buyer order UI. No dependency was added.

### 2026-09-26 15:10 - Add carrier tracking storage

- **Files:** api/db.py, api/market_orders.py, tests/test_market_order_dashboard.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added owner-authorized USPS, UPS, and FedEx tracking storage for shipping orders and dashboard display.
- **Why:** Markets need to associate a real carrier tracking number with a shipment without inventing carrier updates.
- **Verify:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` (3 passed); `git diff --check`.
- **Risk/Notes:** Tracking is stored and displayed only. Carrier API integration and buyer tracking views are deferred. No dependency was added.

### 2026-09-26 15:02 - Add market order fulfillment states

- **Files:** api/db.py, api/market_orders.py, tests/test_market_order_dashboard.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added owner-authorized backend transitions from not started through fulfilling and completion, branching to shipping or ready for pickup based on the stored fulfillment type.
- **Why:** Markets need an enforced fulfillment lifecycle without client-controlled status jumps.
- **Verify:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py -q` (2 passed); `git diff --check`.
- **Risk/Notes:** Added a separate fulfillment status column to preserve Feature 14 rows and avoid rebuilding the existing SQLite orders table. Tracking and buyer status views are not implemented. No dependency was added.

### 2026-09-26 14:52 - Add market order dashboard

- **Files:** api/market_orders.py, api/main.py, tests/test_market_order_dashboard.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added an owner-protected market order listing with purchased item snapshots, totals, fulfillment information, status, and timestamps.
- **Why:** Market owners need a server-authorized view of their own fulfillment work.
- **Verify:** `.venv/bin/python -m pytest tests/test_market_order_dashboard.py tests/test_market_orders.py -q` (5 passed); `git diff --check`.
- **Risk/Notes:** Dashboard is API-only. Status updates, tracking, and buyer order views are not implemented. No dependency was added.

### 2026-09-26 14:40 - Split authorized multi-market carts

- **Files:** api/db.py, api/market_orders.py, api/checkout.py, tests/test_market_orders.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added a market-tagged cart confirmation endpoint that groups lines by market, snapshots each group independently, uses one issuer authorization instruction for the aggregate total, and materializes one private market order per group after verification.
- **Why:** A multi-market cart must give each seller only its own fulfillment work while keeping buyer payment authorization unified.
- **Verify:** `.venv/bin/python -m pytest tests/test_market_orders.py -q` (4 passed); `git diff --check`.
- **Risk/Notes:** Market orders have no dashboard or buyer UI yet. Legacy cart checkout remains separate because its catalog has no market IDs. No dependency was added.

### 2026-09-26 14:28 - Create verified market orders

- **Files:** api/market_orders.py, tests/test_market_orders.py, api/db.py, api/main.py, api/checkout.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added a buyer-authenticated, market-aware checkout confirmation route, pre-authorization market checkout snapshots, durable market orders and order-item snapshots, and issuer-approved order materialization. The existing checkout completion response remains exactly `{verified, transaction_id}` while it now recognizes market instruction IDs internally.
- **Why:** A seller order must preserve the purchased product and fulfillment state and may exist only after the existing Timbre authorization flow verifies payment.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_market_orders.py tests/test_fulfillment_selection.py tests/test_markets.py tests/test_buyer_addresses.py tests/test_buyer_auth.py tests/test_market_products.py tests/test_boundary.py -q` (156 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (329 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** Market shipping is not priced yet, so market total currently equals product subtotal. No inventory reservation, multi-market cart split, buyer order view, or market fulfillment dashboard exists. The existing legacy catalog checkout and payment boundary remain in place. No dependency was added.

### 2026-09-26 14:08 - Add buyer fulfillment selection

- **Files:** api/fulfillment_selection.py, tests/test_fulfillment_selection.py, api/db.py, api/main.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added buyer-authenticated market fulfillment options and a persisted per-buyer, per-market shipping or pickup selection. The server exposes only enabled market capabilities, requires a buyer-owned saved address for shipping, returns pickup information only for active pickup, and protects the database relationship with shape, role, and address-ownership checks. Added PUT to credentialed CORS methods.
- **Why:** Buyers need a validated fulfillment decision before later market-aware order creation can use it.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_fulfillment_selection.py tests/test_markets.py tests/test_buyer_addresses.py tests/test_buyer_auth.py tests/test_market_auth.py tests/test_market_products.py -q` (134 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (326 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** Existing checkout stays unchanged because it operates only on the separate seeded catalog and has no market mapping. This saved selection does not create an order, reserve inventory, authorize payment, or alter Timbre purchase authentication. No dependency was added.

### 2026-09-26 13:45 - Add market shipping settings

- **Files:** api/db.py, api/markets.py, tests/test_markets.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added persisted shipping enablement and canonical per-market USPS, UPS, FedEx, and local-driver method configuration, plus private owner settings routes. Added additive migration and triggers that require a method before shipping can be enabled and preserve an active market's last method. Added configuration, validation, authorization, and direct-invariant tests.
- **Why:** Markets need explicit fulfillment capabilities before checkout can offer a buyer valid shipping or pickup choices.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_markets.py tests/test_market_auth.py tests/test_market_products.py tests/test_buyer_auth.py tests/test_buyer_addresses.py -q` (128 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (320 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** This feature stores methods only. Carrier integrations, buyer fulfillment selection, checkout linkage, orders, and tracking are not implemented. No dependency was added.

### 2026-09-26 13:24 - Add market pickup settings

- **Files:** api/db.py, api/markets.py, tests/test_markets.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added market pickup enablement, one pickup address per market, private owner settings read/update routes, additive migration for the new flag, and database triggers that require an address before pickup can be enabled and prevent active address deletion. Added configuration, authorization, migration, and direct-invariant tests.
- **Why:** Markets need a real pickup location before buyers can later select pickup fulfillment.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_markets.py tests/test_market_auth.py tests/test_market_products.py tests/test_buyer_auth.py tests/test_buyer_addresses.py -q` (118 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (310 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** Pickup management is owner API-only. Buyer-facing pickup information, fulfillment selection, shipping, order creation, and checkout integration are not implemented. No dependency was added.

### 2026-09-26 13:04 - Add buyer shipping addresses

- **Files:** api/buyer_addresses.py (new), tests/test_buyer_addresses.py (new), api/db.py, api/main.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added private buyer-address create and list routes, required shipping-field validation and normalization, optional second line support, a buyer-address database table and index, and a database trigger that rejects non-buyer address ownership. Added privacy, validation, and direct-invariant tests.
- **Why:** Buyers need persistent private shipping addresses before checkout can offer shipping fulfillment.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_buyer_addresses.py tests/test_buyer_auth.py tests/test_market_auth.py tests/test_markets.py tests/test_market_products.py -q` (113 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (305 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** This feature stores and lists addresses only. Editing, removal, pickup, shipping setup, fulfillment selection, orders, and checkout linkage are not implemented. No dependency was added.

### 2026-09-26 12:49 - Add buyer account login

- **Files:** api/buyer_auth.py (new), tests/test_buyer_auth.py (new), api/config.py, api/main.py, api/market_auth.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added buyer registration, login, logout, current-session lookup, a buyer authorization dependency, and a distinct HttpOnly buyer cookie. Reused existing account/session tables, salted scrypt password storage, session digest storage, expiry checks, validation, and CORS behavior. Generalized the existing session lookup to enforce either expected account role server-side.
- **Why:** Buyers need an authenticated shopping identity before private addresses, orders, and fulfillment choices can be added, without replacing merchant authentication or Timbre purchase authorization.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_buyer_auth.py tests/test_market_auth.py tests/test_markets.py tests/test_market_products.py -q` (100 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (292 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** Buyer login is API-only and has no profile, address, order, or checkout integration yet. Market-owner and buyer browser sessions use separate cookies. No dependency or database migration was added.

### 2026-09-26 12:31 - Normalize market product units

- **Files:** api/market_units.py (new), api/market_products.py, tests/test_market_products.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added pure quantity normalization to milligrams for weight, milliliters for volume, and count for count products. Product API responses retain seller display values and now expose normalized quantity, normalized unit, dimension, and normalized quantity per dollar. Added a dimension-safe compatibility helper and conversion, null, and incompatible-dimension tests.
- **Why:** Future marketplace comparison needs compatible measurements in a common base while preserving the seller's original display units and never equating weight, volume, and count.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_market_products.py tests/test_markets.py -q` (86 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (285 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** Normalization does not search or rank products, and it rejects cross-dimension comparisons. No dependency or database column was added.

### 2026-09-26 12:18 - Calculate market product quantity per dollar

- **Files:** api/market_products.py, tests/test_market_products.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added server-derived `quantityPerDollar` to market-product create, list, and update responses. It divides stored quantity by the existing integer-cent USD price, returns null for unmeasured or zero-price products, and is never stored or client-controlled. Added tests for pound, milliliter, and count examples, recalculation after a price edit, null cases, and no derived database column.
- **Why:** Sellers and future commerce comparisons need a current amount-per-dollar value without duplicate mutable state.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_market_products.py tests/test_markets.py -q` (78 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (277 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** The value uses the seller-entered unit and does not compare incompatible dimensions. Feature 8 will add compatible-unit normalization. No dependency or database column was added.

### 2026-09-26 12:10 - Add market product quantity and units

- **Files:** api/db.py, api/market_products.py, tests/test_market_products.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added optional positive numeric product quantities with canonical weight, volume, and count units to the seller-product API and responses. Added complete-pair validation, database constraints and triggers, an additive migration for Feature 4/5 databases, and tests for valid measurements, invalid and incomplete writes, editing and clearing, migration, and direct database enforcement.
- **Why:** Market products need a stable physical amount before quantity-per-dollar calculation and later compatible-unit comparison can be built.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m compileall -q api`; `.venv/bin/python -m pytest tests/test_market_products.py tests/test_markets.py -q` (73 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (272 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `git diff --check`.
- **Risk/Notes:** Quantity is optional, so individually sold products remain supported. Units are validated and stored but are not normalized or compared yet; Feature 7 will calculate quantity per dollar. No dependency was added.

### 2026-09-26 11:43 - Add market product management

- **Files:** api/main.py, api/market_products.py, tests/test_market_products.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added authenticated per-market product listing, partial editing, photo clearing, and permanent product removal. Every route verifies the authenticated owner against the path market, and updates and deletes also require the product to belong to that same market. Added API validation, ownership-isolation, deletion, and no-mutation regression tests. Added DELETE to the existing origin-restricted credentialed CORS policy.
- **Why:** Market owners need to view and manage their catalog while preventing a supplied product ID from crossing market boundaries.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest tests/test_market_products.py tests/test_markets.py tests/test_market_auth.py tests/test_health.py tests/test_boundary.py -q` (91 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (250 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `.venv/bin/python -m compileall -q api tests/test_market_products.py`; `git diff --check`.
- **Risk/Notes:** Product removal is permanent and has no owner UI yet. Products remain separate from the seeded catalog and do not yet appear in storefront, cart, or agent queries. Quantity and unit fields remain deferred to Feature 6. No dependency was added.

### 2026-09-26 11:41 - Add market-owned product creation

- **Files:** api/market_products.py (new), tests/test_market_products.py (new), api/db.py, api/main.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added `POST /markets/{market_id}/products` for authenticated owners, a separate `market_products` table, market ownership checks in the insertion transaction, exact integer-cent storage, required normalized names, nonnegative prices with at most two decimal places, optional safe photo references, and validation and authorization tests. The working seeded `products` catalog was preserved unchanged. Listing, editing, and removal were not added.
- **Why:** Market owners need to create minimal products without fabricating the legacy demo catalog's required merchandising fields or destructively changing its existing cart and voice-shopping behavior.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest tests/test_market_products.py tests/test_markets.py tests/test_market_auth.py tests/test_health.py tests/test_boundary.py -q` (77 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (236 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `.venv/bin/python -m compileall -q api tests/test_market_products.py`; `git diff --check`.
- **Risk/Notes:** Product management is API-only. Market products are intentionally separate from the seeded legacy catalog until a later adapter joins them. They do not yet appear in storefronts, carts, or agent searches. No dependency was added.

### 2026-09-26 11:38 - Add scoped market branding

- **Files:** web/src/pages/MarketStorefront.jsx (new), api/db.py, api/main.py, api/markets.py, tests/test_markets.py, web/src/App.jsx, web/src/components/PageHeading.jsx, web/src/lib/api.js, web/src/lib/router.js, web/src/styles.css, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added persisted market primary colors and optional logo URLs, an additive Feature 2 database migration, public branding reads, owner-authorized branding updates, strict color and logo-reference validation, private owner IDs in public responses, and a public market branding view. The view uses the owner color only for scoped decorative borders and displays generated market initials when no logo exists. No product functionality was added.
- **Why:** Markets need customizable, safely scoped identity without changing Timbre's global theme or requiring a new image-storage system.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest tests/test_markets.py tests/test_market_auth.py tests/test_health.py tests/test_boundary.py -q` (60 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (219 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (67 modules); `.venv/bin/python -m compileall -q api tests/test_markets.py`; `git diff --check`.
- **Risk/Notes:** Branding management is API-only. Logos are referenced by HTTPS URL or root-relative static path; uploads are not implemented because no upload service exists. No dependency was added. Product creation remains unimplemented until Feature 4.

### 2026-09-26 11:31 - Add authenticated market creation

- **Files:** api/markets.py (new), tests/test_markets.py (new), api/db.py, api/main.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added `POST /markets`, which accepts a required market name and derives the persistent owner relationship exclusively from the authenticated market-owner session. Added the `markets` table, owner index, restrictive owner foreign key, database role trigger, normalized name validation, and tests for creation, persistence, authentication, spoofing, validation, and database invariants. No branding, product, buyer, order, or fulfillment functionality was added.
- **Why:** A market must be created only by a valid authenticated owner and must never become anonymous or orphaned.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest tests/test_markets.py tests/test_market_auth.py tests/test_health.py tests/test_boundary.py -q` (47 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (206 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (66 modules); `git diff --check`.
- **Risk/Notes:** This feature is API-only. Market listing and administration UI are not implemented. Market branding is reserved for Feature 3. No dependency was added; the new module uses Python standard-library UUID and datetime support plus already-pinned FastAPI and Pydantic.

### 2026-09-26 11:28 - Add market-owner account authentication

- **Files:** api/market_auth.py (new), tests/test_market_auth.py (new), api/db.py, api/config.py, api/main.py, .env.example, AGENTS.md, docs/CHANGELOG.md.
- **What:** Added merchant-side market-owner registration, login, logout, current-session lookup, and a reusable server-side authorization dependency. Added account and expiring session tables, salted scrypt password hashing, digest-only session storage, an HttpOnly SameSite cookie, environment settings, credentialed same-origin CORS, and focused tests. No market, product-management, buyer, order, or fulfillment feature was added.
- **Why:** Multi-market work must start with an authenticated owner identity so later market creation cannot be anonymous or orphaned, while preserving the separate issuer and Timbre purchase-authorization boundary.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest tests/test_market_auth.py tests/test_health.py tests/test_boundary.py -q` (40 passed); `.venv/bin/python -m pytest tests/test_guards.py -q` (7 passed); `.venv/bin/python -m pytest -q` (199 passed, 2 pre-existing fresh-interpreter guards abort only in combined macOS suite order and pass in isolation); `npm --prefix web run build` (66 modules); `git diff --check`.
- **Risk/Notes:** This feature is API-only. Market creation is not implemented. Buyer authentication is not implemented even though the role value is reserved in the schema. Set `MARKET_SESSION_COOKIE_SECURE=true` under production HTTPS. No external dependency was added because the new cryptographic and token imports are Python standard library modules.

### 2026-09-26 16:15 - Make the header voice button start agentic shopping

- **Files:** web/src/components/SiteHeader.jsx, web/src/components/jump.js, web/src/components/AgenticVoiceShopping.jsx, web/src/components/VoiceShopping.jsx, AGENTS.md.
- **What:** Replaced the header button's focus-only action with a launcher that prioritizes the agentic microphone and clicks it after scrolling and focusing. Added stable agentic control ids, route waiting, and active-recorder guards. If the agentic panel is absent, the launcher starts the existing Whisper microphone. If an agentic service returns 503 after capture, a cancelable in-page handoff sends the same WAV to the existing `shoppingVoice` request and `VoiceShopping` confirmation UI.
- **Why:** The header control appeared actionable but only moved focus, and an unavailable agentic provider otherwise forced the shopper to find the legacy panel and repeat the request.
- **Verify:** `npm --prefix web run build` (66 modules); run the isolated Node launcher check for agentic priority, legacy DOM fallback, active-recorder guarding, and WAV handoff dispatch; `git diff --check`. In the browser, click the header button on the shop page and confirm the agentic button changes to Stop recording. With the agentic panel removed or unavailable, confirm the legacy panel starts or receives the captured WAV.
- **Risk/Notes:** Automatic WAV fallback is limited to HTTP 503 service-unavailable responses. Validation errors remain visible in the agentic panel because replaying malformed or silent audio through Whisper would not help. No backend, dependency, issuer, authentication, checkout, payment, or cart behavior changed.

### 2026-09-26 16:00 - Treat affordability language as price ranking

- **Files:** api/commerce_agent.py, api/openai_intent.py, tests/test_commerce_agent.py, tests/test_agentic_basket.py, AGENTS.md.
- **What:** Added a deterministic commerce guard that removes affordability language from hard catalog requirements and uses it to rank relevant matches by price. A requirement made only of price language is discarded; actual properties beside it remain enforced. The OpenAI extraction instructions now explicitly keep affordability language out of requirements and optional preferences. Added single-item and basket regressions, including the exact contradictory shape that caused `Very cheap yogurt.` to fail.
- **Why:** OpenAI could emit both `preferCheapest: true` and `importantRequirements: ["cheap"]`, causing commerce to reject every product because catalog descriptions do not say cheap.
- **Verify:** `.venv/bin/python -m pytest -q tests/test_commerce_agent.py tests/test_agentic_basket.py tests/test_agentic_intent.py tests/test_ambiguity_resolution.py tests/test_final_intent.py` (56 passed); `make test` (194 passed); `npm --prefix web run build`; live POST of `Very cheap yogurt.` through `/agentic-shopping/basket/intent`, `/clarifications`, and `/prepare` returns `cart_ready` with Chobani Greek Yogurt, Nonfat Plain; `git diff --check`.
- **Risk/Notes:** This ranks the cheapest relevant catalog match; it does not invent a dollar ceiling. The existing No price limit assumption remains visible when the shopper does not state one. No dependency was added. The two existing SpeechBrain `torch.load` future warnings remain.

### 2026-09-26 15:30 - Agentic baskets: several items and meals in one request

- **Files:** api/basket.py (new), api/openai_intent.py, api/agentic_shopping.py, api/ambiguity_resolution.py, api/config.py, web/src/components/AgenticVoiceShopping.jsx, web/src/lib/api.js, web/src/lib/shoppingRecorder.js, web/src/styles.css, tests/test_agentic_basket.py (new), tests/test_ambiguity_resolution.py, docs/DECISIONS.md, AGENTS.md.
- **What:** Added `/agentic-shopping/basket/{intent,clarifications,clarifications/answer,prepare}` (ADR 11). One Structured Outputs call extracts a `BasketIntent`: named items (each a `ShoppingIntent` run through the unchanged single-item policy), meals (goal, servings, ingredients with catalog ids or null, dietary needs the catalog cannot verify), and one optional basket budget. Clarification is per item, labeled by item, and answers touch only that item. `prepare_basket` counts fixed-quantity items and meal lines first in spoken order, then lets "as many as fit" items share what is left of the basket budget; meal ids are checked against the catalog and unknown ids become "not sold here"; an item whose words the shopper never said is treated as agent-chosen; going over the basket budget is shown, never silently trimmed. Named-only baskets are applied directly with Undo; any agent-chosen line returns `needs_confirmation`, and the UI shows a review list with Remove and Put back (re-priced by the server) and Add to cart. The agentic recording limit is 25 seconds (agentic path only; the Whisper path and issuer keep 10). Extraction failures are logged server side by cause (HTTP status or schema field), never with the transcript. The single-item endpoints remain for compatibility.
- **Why:** The person asked for several items per request and for goal requests such as "buy me things to make a tuna salad".
- **Verify:** `.venv/Scripts/python.exe -m pytest -q` (192 passed); `npm --prefix web run build`; live OpenAI runs through the basket routes: "buy me things to make a tuna salad" proposes 2 Wild Planet Albacore Tuna plus optional bread, and lists mayonnaise, celery, onion, lemon juice, salt, and pepper as not sold here; "get me stuff for tuna salad, and two cokes, under 20 bucks" gives the Coca-Cola item plus the tuna salad meal in 3 of 3 runs, flagging $25.45 over the $20 limit when the optional bread was included; "milk, eggs, and bread" goes straight to the cart; "breakfast for four people, no nuts" proposes eggs, bread, bacon, and juice and marks "no nuts" as unverifiable; "something for dinner" asks for items or a dish.
- **Risk/Notes:** Meal quality depends on the model; the catalog check, review step, and budget check bound it. The seeded catalog lacks most tuna salad ingredients, which the list now states. One burst of six 503s occurred before logging was added and did not recur; if it does, the server log names the cause. Not yet spoken through the browser.

### 2026-09-26 14:15 - Agentic shopping understands budgets, per-item limits, and "cheapest"

- **Files:** api/openai_intent.py, api/ambiguity_resolution.py, api/final_intent.py, api/commerce_agent.py, web/src/components/AgenticVoiceShopping.jsx, tests/test_agentic_intent.py, tests/test_final_intent.py, tests/test_commerce_agent.py, AGENTS.md.
- **What:** Added `quantity.mode` (`exact` or `fill_budget`), `maxPrice.per` (`total` or `each`), and `preferCheapest` to the intent schema; a `strict_schema` helper makes every property required and strips defaults for Structured Outputs, while model defaults keep older client-carried state valid. "As much X as I can under $10" becomes fill_budget: the commerce agent computes floor(limit / unit price) per candidate, capped by MAX_QUANTITY minus what the cart already holds, and says "as many as fit in $10.00, before tax and delivery". A fill-budget request with no budget asks one question, "How much do you want to spend in total?". Per-item limits check one unit. "Cheapest" sorts by price only within the most relevant tier, so it never swaps a jar of peanut butter for an energy bar. The prompt counts packages as sold ("a dozen eggs" is 1 carton) and writes products in catalog words ("coke" as Coca-Cola). Size also matches pack sizes in the product name ("6 Pack"). Labels no longer repeat a brand the name already contains. The UI shows "As many as fit your limit", "$2 each", and "Cheapest match", and the ready card shows the agent's message plus the cart total.
- **Why:** The person asked for quantity to be inferred from phrases like "buy as much of X as you can but keep it under 10 bucks".
- **Verify:** `.venv/Scripts/python.exe -m pytest -q` (all pass); `npm --prefix web run build`; live OpenAI text runs: "buy as much greek yogurt as you can but keep it under 10 bucks" adds 6 Chobani Vanilla Greek Yogurt ($8.94); "as many cans of chicken soup as twenty dollars will buy" adds 13 ($19.37); "fill up fifteen dollars of pasta" adds 7 ($13.93); "yogurt, but no more than two dollars each" and "a dozen eggs" and "a six pack of coke" add 1; "as much ice cream as I can get" asks only for the budget. All with 0 questions otherwise.
- **Risk/Notes:** The budget covers item prices; tax and delivery are added at checkout, and the message says so. Not yet spoken through the browser.

### 2026-09-26 13:30 - Agentic shopping asks only when unsure

- **Files:** api/ambiguity_resolution.py, api/final_intent.py, api/commerce_agent.py, api/openai_intent.py, api/config.py, web/src/components/AgenticVoiceShopping.jsx, tests/test_agentic_intent.py, tests/test_ambiguity_resolution.py, tests/test_final_intent.py, tests/test_commerce_agent.py, docs/DECISIONS.md, AGENTS.md.
- **What:** Replaced the confirm-every-field policy (a live request took 5 confirmations) with ADR 10. High-confidence values are accepted without questions; only the product is required; an unstated quantity defaults to 1 and an unstated budget means no limit, both disclosed on screen. Medium or low values and model-flagged material ambiguities get one Yes/No each, with uniform wording, one question per field and per span of words. Added a deterministic catalog-aware brand repair (the planned boys/Bose fix): a heard word that sounds like or is spelled like a store brand is proposed once, never accepted without a Yes, and the same words are set aside from use case and preferences; declining gives them back. A store brand the speaker never said (inferred from the product, as "OJ" to Simply Orange) is neither asked nor used. The intent prompt now receives the store catalog as reference data, keeps the product as the spoken generic phrase, and treats price and quantity as optional. Finalization normalizes spoken currency ("dollars" was being rejected as a foreign currency). Commerce treats color as a disclosed soft preference, accepts no price limit, prefers names that are mostly the request (peanut butter picks the jar, not the energy bar), matches split compounds (gold fish to Goldfish), and explains which constraint ruled everything out. The UI shows only what was said plus assumptions, applies a clear request straight to the cart, and adds Undo.
- **Why:** The shopper had to confirm every field, including ones heard clearly, which is the opposite of what a person with a speech disability needs.
- **Verify:** `.venv/Scripts/python.exe -m pytest -q` (174 passed); `npm --prefix web run build`; live OpenAI text runs through `/agentic-shopping/intent`, `/clarifications`, `/finalize`, `/commerce/prepare-cart`: "two OJs", "I need some red apples", "a couple of greek yogurts under five bucks", "three cans of chicken noodle soup", "some ben and jerrys ice cream", "I want some Gold fish crackers" reach cart_ready with 0 questions; "get me some jiffy peanut butter" asks only `I heard "jiffy". Did you mean Jif?`; "coffee under three dollars" explains Folgers costs $5.99, over the $3.00 limit.
- **Risk/Notes:** Nothing is bought without the existing checkout, issuer challenge, and payment; the merchant boundary is unchanged. Auto-applying to the cart relies on Undo and cart review as the confirmation. The seeded catalog sells no bananas, so the banana example now reports that honestly. Not yet spoken end to end through the browser after this change.

### 2026-09-26 12:30 - Record the first human passkey and Stripe purchase

- **Files:** AGENTS.md, docs/CHANGELOG.md.
- **What:** Recorded that a person completed a fingerprint passkey registration and a passkey-only UI purchase through Stripe test mode; the merchant response was exactly `{verified, transaction_id}`. Recorded the first failure and its cause: the Windows WebAuthN operational log showed the passkey was held by Edge's Microsoft Password Manager and Windows routed the assertion to it as a plugin provider (`PluginGetAssertionRequest`); user verification passed but no assertion returned, so the issuer never received a response. The stale credential row was removed from the local `issuer.db` (demo data only) and the person re-registered.
- **Why:** These were the two items listed as unverified by a human, and the failure mode can recur on a demo machine.
- **Verify:** Enroll a passkey for a demo cardholder, check out, choose Use my passkey, and confirm the merchant response in devtools has exactly two keys.
- **Risk/Notes:** No application code changed. The web page cannot force Windows Hello over a browser passkey provider, so the demo machine needs one rehearsal.

### 2026-09-26 12:00 - Record ADR 5: high-value purchases fall back to the passkey alone

- **Files:** docs/DECISIONS.md, tests/test_challenge.py, AGENTS.md, docs/CHANGELOG.md.
- **What:** The person confirmed that purchases at or above `STEP_UP_AMOUNT` ($50) fall back to the passkey alone after 2 failed voice attempts. Recorded as ADR 5 (accepted), updated ADR 6's forward reference, marked the decision closed in the AGENTS.md handoff, and added a regression test for the previously untested step-up plus two-failures path.
- **Why:** The behavior already existed in `issuer/approvals.py` but was an open decision with no test; it is now a recorded decision enforced by the suite.
- **Verify:** `.venv/Scripts/python.exe -m pytest -q tests/test_challenge.py` (15 passed).
- **Risk/Notes:** No application code or §7 parameter changed.

### 2026-09-26 11:45 - Record live agentic text-stage simulations

- **Files:** AGENTS.md, docs/CHANGELOG.md.
- **What:** Recorded two live OpenAI intent and clarification simulations that deliberately skipped speech transcription. The banana request completed confirmation, finalization, catalog selection, and cart preparation successfully. The boys-headphones request was held at medium-confidence clarification and supported a targeted correction after rejection, but misclassified `boys` as use case and optional preference instead of proposing Bose as a possible brand transcription. Added a non-implemented plan for catalog-aware candidate generation and source-span deduplication.
- **Why:** The requested simulations needed to verify whether a likely recognition error is surfaced instead of silently becoming confirmed commerce intent.
- **Verify:** Start the merchant API with `.venv/bin/python -m uvicorn api.main:app --port 8000 --env-file .env`; post each supplied transcript to `/agentic-shopping/intent`; post the response to `/agentic-shopping/clarifications`; confirm the first returns product, maximum price, and quantity questions and reaches `cart_ready` after confirmation; confirm the second asks about medium-confidence `boys` and asks for a single-field correction after rejection.
- **Risk/Notes:** The safety behavior passed because the uncertain value blocks finalization until confirmed or corrected. Semantic repair remains incomplete because Bose was not proposed and one heard span produced two optional-field questions. The improvement plan is documentation only. No application code, dependency, Whisper path, cart, authentication, checkout, issuer, or payment behavior changed.

### 2026-09-26 11:30 - Complete additive agentic voice shopping flow

- **Files:** web/src/components/AgenticVoiceShopping.jsx (new), web/src/App.jsx, web/src/pages/Shop.jsx, web/src/lib/api.js, web/src/lib/cart.jsx, web/src/styles.css, AGENTS.md.
- **What:** Added the separate full-request voice panel and connected every existing agentic backend stage in order: shared audio capture, OpenAI transcription, structured intent extraction, targeted clarification, final intent, commerce selection, and validated cart application. The panel preserves and displays the raw transcript separately, shows extracted fields, verifies item, quantity, price, and every supplied optional preference, accepts a correction for only the active field, reports progress and failures, and exposes Review cart and Continue to checkout only after Cart Ready. Cart replacement validates the complete payload and refuses to overwrite concurrent cart edits. The existing Whisper panel and `/shopping/voice` path remain present and unchanged.
- **Why:** Features 6 through 10 complete the additive speech-to-commerce experience while preserving the existing cart, authentication, issuer, payment, checkout, and Whisper implementations.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py tests/test_agentic_intent.py tests/test_ambiguity_resolution.py tests/test_final_intent.py tests/test_commerce_agent.py` (27 passed); `make test` outside the restricted process sandbox (159 passed); `npm --prefix web run build` (66 modules); `git diff --check`; open `http://localhost:5173/` and confirm both Shop by voice panels appear, with the new full-request panel below the existing one.
- **Risk/Notes:** A live OpenAI round trip was not run because it requires a valid backend-only `OPENAI_API_KEY`. Provider calls are covered by mocked tests. The agent cannot create an instruction, authenticate, contact the issuer, approve payment, or place an order; it stops at Cart Ready and uses the existing checkout. No new dependency was added. The full suite retains two pre-existing SpeechBrain `torch.load` future warnings.

### 2026-09-26 11:15 - Agentic shopping Feature 5: commerce agent and prepared cart

- **Files:** api/commerce_agent.py (new), api/agentic_shopping.py, web/src/lib/api.js, tests/test_commerce_agent.py (new), AGENTS.md.
- **What:** Added `POST /agentic-shopping/commerce/prepare-cart`. The deterministic commerce adapter searches and ranks the existing catalog against the finalized product, brand, size, merchant, USD budget, quantity, and important requirements; refuses unsupported color variants and other hard mismatches; merges the selected quantity with caller-supplied existing cart lines; and prices the complete result through the existing server cart pricer. No-match responses preserve existing items. Use-case and optional-preference limitations are returned explicitly. Added a frontend API adapter that sends the current CartProvider lines and receives the full prepared cart.
- **Why:** Feature 5 connects confirmed structured intent to real catalog selection and the existing browser-cart contract without creating a second catalog, cart, or pricing implementation.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py tests/test_agentic_intent.py tests/test_ambiguity_resolution.py tests/test_final_intent.py tests/test_commerce_agent.py` (27 passed); `make test` outside the restricted process sandbox (159 passed); `npm --prefix web run build`.
- **Risk/Notes:** The current agentic UI is not built, so no component applies the returned lines to CartProvider yet. The endpoint prepares and prices the full replacement payload but does not persist browser state. It cannot call checkout, the issuer, authentication, or payment. Catalog metadata has no color field, so color-constrained requests return no match. No new dependency was added. The existing Whisper shopping UI and purchase flow were not changed.

### 2026-09-26 11:00 - Catalog grows to 56 products with clean, uniform photos

- **Files:** scripts/seed_catalog.json, web/public/products/ (39 added, 7 deleted, the rest re-normalized), scripts/seed_demo.py, web/src/pages/Shop.jsx (`SECTIONS`), web/src/styles.css. Catalog work by a helper agent; reviewed on a contact sheet.
- **What:**
  - **Catalog:** 56 real US grocery products (up from 18) across ten aisles. The six products with no clean photo were dropped (Dole bananas, GoGo SqueeZ, Café Bustelo, Chobani nonfat 32 oz, Terra Delyssa, S.Pellegrino), and eight existing photos were replaced with cleaner Open Food Facts images.
  - **Photos:** every photo is an Open Food Facts image (CC BY-SA 3.0), viewed before acceptance and normalized to a 600x600 white-padded progressive JPEG under 70 KB (2.7 MB total).
  - **Seeding:** `seed_demo` now deletes products the JSON no longer lists, so re-seeding never leaves a removed item with a missing photo and does not need `make reset` (which would wipe enrollments).
  - **Product names:** two names were adjusted to what shoppers say ("Butter, Unsalted", "Penne Pasta") so the keyword fallback suggests them for "butter" and "pasta".
  - **Aisle chips:** no longer sticky. Ten chips wrap to two or three rows, and a 115 to 168px bar under the header would have hidden focused headings (WCAG 2.4.11).
- **Why:** The user asked for more food items and better images. AGENTS.md §1.1 said "about 20"; this expands it at the user's request.
- **Verify:** `python -m scripts.seed_demo` prints "catalog: 56 products" and the running catalog has no missing photos; `make test` (132 passed); `npm --prefix web run build`. At 1440px there is no horizontal scroll and chip jumps land headings at 130px, below the 64px header. Voice probes (typed): milk, eggs, coffee, chips, orange juice, strawberries, bacon are confident; butter, pasta, bread, ice cream ask a yes/no question.
- **Risk/Notes:** Prices are hand-set estimates. A few sizes were read off the package. Weaker photos: the Kirkland shrimp and Folgers crops, Dave's 21 Grains (tight crop), and a faint grey behind Sriracha and the prosciutto. There are no bananas, since Open Food Facts had no clean shot.

### 2026-09-26 11:00 - Verify all supplied constraints with three mandatory fields

- **Files:** api/ambiguity_resolution.py, api/final_intent.py, api/openai_intent.py, tests/test_ambiguity_resolution.py, tests/test_final_intent.py, AGENTS.md.
- **What:** Revised Feature 3 to verify every supplied request aspect before finalization. Product, quantity, and maximum price are mandatory and generate an open correction question when missing. Brand, size, color, merchant, use case, important requirements, and optional preferences are optional when absent, but generate Yes/No confirmation when supplied. Rejection still asks for only that field. Feature 4 now requires typed product, price, and quantity while leaving absent optional fields empty. The extraction prompt documents the same required/optional boundary.
- **Why:** The user requires full request verification while keeping brand, size, color, merchant, use case, and similar refinements optional.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py tests/test_agentic_intent.py tests/test_ambiguity_resolution.py tests/test_final_intent.py` (21 passed); `make test` outside the restricted process sandbox (153 passed); `npm --prefix web run build`.
- **Risk/Notes:** A detailed request now creates one targeted confirmation per supplied field, which is intentionally more thorough but adds interaction steps. Missing optional fields do not create questions or block finalization. No new dependency was added. Existing Whisper, cart, issuer, authentication, and checkout code remains unchanged.

### 2026-09-26 10:45 - Agentic shopping Feature 4: final structured intent

- **Files:** api/final_intent.py (new), api/ambiguity_resolution.py, api/openai_intent.py, api/agentic_shopping.py, tests/test_final_intent.py (new), AGENTS.md.
- **What:** Added `POST /agentic-shopping/finalize`, which recomputes client-carried clarification state and produces a typed final shopping request from high-confidence extracted fields and confirmed or corrected values. It refuses pending, missing, unclear, and non-shopping requests; omits unconfirmed medium or low-confidence values; validates finite nonnegative prices and positive whole quantities; and retains the raw transcript, original extraction, and clarification answers beside the final request. Feature 2 now instructs OpenAI to use exact schema field names for missing information, and Feature 3 turns those declared missing fields into targeted questions.
- **Why:** Feature 4 creates the safe handoff object that a commerce agent can consume without treating unresolved model guesses as facts.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py tests/test_agentic_intent.py tests/test_ambiguity_resolution.py tests/test_final_intent.py` (21 passed); `make test` outside the restricted process sandbox (153 passed); `npm --prefix web run build`.
- **Risk/Notes:** The endpoint is backend-only and does not yet search products or populate the cart. It recomputes answers against the supplied original extraction but does not persist or sign client-carried state; Feature 5 must still validate the typed final request at its commerce boundary. No new third-party import was added, so `requirements.txt` did not change. Existing Whisper, cart, issuer, authentication, and checkout files were not changed.

### 2026-09-26 10:30 - Agentic shopping Feature 3: ambiguity resolution

- **Files:** api/ambiguity_resolution.py (new), api/agentic_shopping.py, tests/test_ambiguity_resolution.py (new), AGENTS.md.
- **What:** Added client-carried clarification state and separate start/answer endpoints. The resolver asks only about material ambiguous fields, presents Yes/No for a proposed interpretation, converts rejection into a short correction question for that field, and asks for a missing critical product. It retains the exact raw transcript, original structured extraction, per-field answers, separately resolved values, and pending questions. Invalid, stale, unsupported, empty, or unrelated answers fail with 422. It does not call OpenAI, search products, alter the cart, contact the issuer, or finalize intent.
- **Why:** Feature 3 lets users repair one uncertain field without repeating a full request and prevents unresolved model guesses from becoming shopping facts.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py tests/test_agentic_intent.py tests/test_ambiguity_resolution.py` (15 passed); `make test` outside the restricted process sandbox (147 passed); `npm --prefix web run build`.
- **Risk/Notes:** The endpoints are not connected to the UI yet. State is carried by the client to fit the existing React local-state pattern and is recomputed before each answer. Feature 4 must create a typed final intent and must refuse incomplete clarification state. No third-party imports were added, so `requirements.txt` did not change for this feature. Existing Whisper, cart, issuer, authentication, and checkout files were not changed.

### 2026-09-26 10:15 - Pin direct intent-schema dependency

- **Files:** requirements.txt.
- **What:** Added the installed Pydantic 2.13.5 version as an explicit dependency because the agentic intent schema imports Pydantic directly rather than relying on FastAPI to install it transitively.
- **Why:** Direct imports should be reproducible from `requirements.txt` on a clean system.
- **Verify:** `.venv/bin/python -m pip install -r requirements.txt`; `.venv/bin/python -m pip check`; `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py tests/test_agentic_intent.py`; `make test`.
- **Risk/Notes:** No application behavior changed. Standard-library imports need no package entry, and all other third-party imports used by Features 1 and 2 were already pinned directly.

### 2026-09-26 10:10 - Full demo run: fixes for the details (a11y review, titles, favicon, cart races)

- **Files:** web/index.html, web/public/favicon.svg (new), web/src/App.jsx, web/src/lib/{cart.jsx,api.js}, web/src/components/{VoiceShopping,ProductCard,CartDrawer,SiteHeader}.jsx, web/src/components/CheckoutSteps.jsx (new), web/src/pages/{Shop,Checkout,Receipt}.jsx, web/src/styles.css, web/src/styles/checkout.css, api/catalog.py (`GET /store`), tests/test_shopping.py. Most of these landed in the teammate commit "2:55 am" (2cd529c) without an entry; this entry covers them and the remaining Shop.jsx changes.
- **What:** From a scripted end-to-end run in the browser plus an independent accessibility review:
  - The store had no favicon (404) and one page title everywhere. It now has an SVG favicon, a theme color, a description, and a title per route (WCAG 2.4.2).
  - Cart updates were computed from the rendered state, so taps faster than a re-render were lost. They are now functional (`adjust`).
  - "Added one X" was announced twice. The voice panel's status line is now the only channel.
  - A suggestion at the maximum quantity silently dropped focus. "Yes" now uses `aria-disabled`, and both the question and a press explain why.
  - Spoken readback could overlap a screen reader. A remembered "Read suggestions aloud after I speak" switch now controls it, and "Say it again" stays available.
  - The card and drawer steppers handled the maximum differently. Both now use `aria-disabled` and announce the limit.
  - The drawer's quantity used a prohibited `aria-label` on a span. It now uses visually hidden text.
  - The header's "Shop by voice" was a link, hidden below 900px. It is now a button, icon-only below 600px.
  - Aisle chips were links that never navigated. They are now buttons.
  - The receipt had no step list and a table that could not reflow at 320px (WCAG 1.4.10). Both are fixed; the step list is shared as `CheckoutSteps`.
  - The hero's "$35" was a second copy of the merchant threshold. It now comes from `GET /store` and the pill hides if that fails.
  - The footer credit now links Open Food Facts and the CC BY-SA 3.0 license, and says prices are illustrative.
- **Why:** The user asked for a full test pass with attention to the small details.
- **Verify:** `make test` (132 passed); `npm --prefix web run build`. Browser checks: at 20 the stepper is `aria-disabled` with a visible note; back at 0, focus returns to Add; Escape and Remove handle focus; Cancel in the bank widget returns focus to Approve with a message; `/checkout/complete` returned 40 bytes (`verified`, `transaction_id` only); Baseline audio is served; bad routes and bad receipt ids degrade cleanly; the phone header stays 64px with a 44px voice button.
- **Risk/Notes:** Not verifiable headless: real microphone capture, Windows Hello, and a screen reader's handling of "Payment approved" versus the receipt heading focus (review item 8, left for a manual NVDA check).

### 2026-09-26 10:00 - Agentic shopping Feature 2: structured intent extraction

- **Files:** api/openai_intent.py (new), api/agentic_shopping.py, api/config.py, tests/test_agentic_intent.py (new), AGENTS.md.
- **What:** Added a separate `POST /agentic-shopping/intent` backend stage using OpenAI `gpt-4.1-mini` with strict JSON Schema Structured Outputs. It returns the unchanged raw transcript beside a locally validated interpretation of product, brand, maximum price, quantity, size, color, merchant preference, use case, requirements, optional preferences, missing information, and material ambiguities. Every scalar field carries confidence and exact supporting source text. Possible recognition mistakes keep both the heard text and an unconfirmed proposal. The prompt treats transcripts as untrusted data, OpenAI response storage is disabled, invalid model output is rejected, and provider details are not exposed.
- **Why:** Feature 2 requires commerce interpretation to remain distinct from transcription and to surface uncertainty before any shopping action.
- **Verify:** `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py tests/test_agentic_intent.py` (10 passed); `make test` outside the restricted process sandbox (142 passed); `npm --prefix web run build`; OpenAPI contains both additive routes and both existing Whisper shopping routes.
- **Risk/Notes:** No live OpenAI request was made because no `OPENAI_API_KEY` was supplied. The intent route is not connected to the UI and does not yet resolve ambiguities, finalize intent, search products, or populate the cart. `api/asr.py`, `api/llm.py`, `api/shopping.py`, the existing voice-shopping UI, cart, issuer, authentication, and checkout were not changed.

### 2026-09-26 09:30 - Agentic shopping Feature 1: OpenAI transcription

- **Files:** api/openai_transcription.py (new), api/agentic_shopping.py (new), api/config.py, api/main.py, .env.example, tests/test_agentic_transcription.py (new), AGENTS.md.
- **What:** Added a separate `POST /agentic-shopping/transcribe` backend route that validates the existing recorder's mono 16 kHz WAV and sends it to OpenAI `gpt-4o-transcribe`. The dedicated service returns the provider transcript exactly, with no trimming, normalization, shopping reasoning, catalog access, cart mutation, issuer call, or audio persistence. Missing keys, empty/silent/malformed audio, provider failures, malformed responses, and empty transcripts return actionable errors without exposing provider details.
- **Why:** Feature 1 of the additive OpenAI agentic-purchase pipeline requires an isolated audio-to-text stage while preserving the working local Whisper flow.
- **Verify:** `.venv/bin/python -m pytest -q tests/test_agentic_transcription.py` (5 passed); `make test` (137 passed); `npm --prefix web run build`; OpenAPI contains `/shopping/voice`, `/shopping/text`, and `/agentic-shopping/transcribe`.
- **Risk/Notes:** No live OpenAI call was made because no `OPENAI_API_KEY` was supplied. The new endpoint is not connected to the UI yet. `api/asr.py`, `/shopping/voice`, `/shopping/text`, and `VoiceShopping.jsx` were not changed. No new dependency was added; the service uses pinned `httpx`. During verification, the route-preservation test was adjusted to inspect FastAPI's generated OpenAPI paths because this FastAPI version stores included routers behind internal route markers; application behavior was unaffected.

---


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
