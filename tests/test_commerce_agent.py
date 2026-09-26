"""Feature 5: finalized intent to catalog selection and prepared cart."""
from copy import deepcopy

from fastapi.testclient import TestClient

from api import agentic_shopping, commerce_agent
from api.commerce_agent import CommerceRequest, CommerceResult, prepare_commerce_cart, search_products
from api.final_intent import FinalShoppingIntent, FinalizedShoppingRequest
from api.main import app
from tests.test_agentic_intent import intent_payload


CATALOG = [
    {
        "id": "chobani", "name": "Greek Yogurt, Nonfat Plain", "brand": "Chobani",
        "size": "32 oz", "category": "dairy", "price_cents": 649,
        "image_url": "/chobani.jpg", "image_credit": "test",
    },
    {
        "id": "fage", "name": "Total 0% Greek Yogurt", "brand": "Fage",
        "size": "32 oz", "category": "dairy", "price_cents": 749,
        "image_url": "/fage.jpg", "image_credit": "test",
    },
    {
        "id": "bananas", "name": "Organic Bananas", "brand": "Dole",
        "size": "3 lb", "category": "produce", "price_cents": 299,
        "image_url": "/bananas.jpg", "image_credit": "test",
    },
]


def final_intent(**changes):
    values = {
        "product": "yogurt", "brand": None, "maxPrice": 20, "currency": "USD",
        "quantity": 2, "size": None, "color": None, "merchantPreference": None,
        "useCase": None, "importantRequirements": [], "optionalPreferences": [],
    }
    values.update(changes)
    return FinalShoppingIntent(**values)


def finalized(intent=None):
    return FinalizedShoppingRequest(
        rawTranscript="raw",
        extractedIntent=intent_payload(),
        clarificationAnswers={},
        finalIntent=intent or final_intent(),
    )


def test_search_filters_brand_size_budget_and_requirements():
    matches, reason = search_products(
        final_intent(brand="Chobani", size="32 oz", importantRequirements=["nonfat"]),
        CATALOG,
    )
    assert reason is None
    assert [match.product.id for match in matches] == ["chobani"]

    too_small_budget, _ = search_products(final_intent(maxPrice=10), CATALOG)
    assert too_small_budget == []  # two units cost more than $10


def test_color_is_a_preference_disclosed_when_the_catalog_cannot_confirm_it():
    colored, reason = search_products(final_intent(color="blue"), CATALOG)
    assert reason is None and colored
    assert commerce_agent._unverified_preferences(final_intent(color="blue"), colored[0].product) == [
        "color: blue"
    ]


def test_no_price_limit_and_ranking_prefers_names_that_are_mostly_the_request():
    catalog = CATALOG + [
        {"id": "bar", "name": "Crunchy Peanut Butter Energy Bar", "brand": "Clif Bar", "size": "2.4 oz",
         "category": "snacks", "price_cents": 149, "image_url": "/bar.jpg", "image_credit": "test"},
        {"id": "jar", "name": "Creamy Peanut Butter", "brand": "Jif", "size": "16 oz",
         "category": "pantry", "price_cents": 349, "image_url": "/jar.jpg", "image_credit": "test"},
    ]
    matches, reason = search_products(final_intent(product="peanut butter", maxPrice=None, quantity=1), catalog)
    assert reason is None
    assert [match.product.id for match in matches] == ["jar", "bar"]


def test_as_many_as_fit_counts_units_within_the_limit_and_store_maximum(monkeypatch):
    fill = final_intent(product="yogurt", maxPrice=10, quantity=None, quantityMode="fill_budget")
    matches, reason = search_products(fill, CATALOG)
    assert reason is None
    assert [(m.product.id, m.quantity) for m in matches] == [("chobani", 1), ("fage", 1)]

    cheap = final_intent(product="bananas", maxPrice=10, quantity=None, quantityMode="fill_budget")
    assert search_products(cheap, CATALOG)[0][0].quantity == 3            # $2.99 x 3 = $8.97
    assert search_products(cheap, CATALOG, {"bananas": 19})[0][0].quantity == 1   # store maximum is 20
    assert search_products(cheap, CATALOG, {"bananas": 20})[1] ==         "Your cart already has the most allowed of Dole Organic Bananas."

    monkeypatch.setattr(commerce_agent, "list_catalog", lambda: CATALOG)
    monkeypatch.setattr(commerce_agent, "price_cart", lambda lines: {"total_cents": 0})
    result = prepare_commerce_cart(CommerceRequest(finalizedRequest=finalized(cheap)))
    assert result.addedQuantity == 3
    assert result.message == ("Added 3 × Dole Organic Bananas ($2.99 each, $8.97 total) to your cart. "
                              "That is as many as fit in $10.00, before tax and delivery.")


def test_a_per_item_limit_checks_one_unit_and_cheapest_stays_relevant():
    each = final_intent(product="yogurt", maxPrice=7, pricePer="each", quantity=2)
    assert [m.product.id for m in search_products(each, CATALOG)[0]] == ["chobani"]   # $6.49 <= $7 each
    assert search_products(final_intent(product="yogurt", maxPrice=6, pricePer="each"), CATALOG)[1] ==         "The lowest-priced match, Chobani Greek Yogurt, Nonfat Plain, costs $6.49, over your $6.00 each limit."

    catalog = CATALOG + [
        {"id": "bar", "name": "Crunchy Peanut Butter Energy Bar", "brand": "Clif Bar", "size": "2.4 oz",
         "category": "snacks", "price_cents": 149, "image_url": "/bar.jpg", "image_credit": "test"},
        {"id": "jar", "name": "Creamy Peanut Butter", "brand": "Jif", "size": "16 oz",
         "category": "pantry", "price_cents": 349, "image_url": "/jar.jpg", "image_credit": "test"},
        {"id": "jar2", "name": "Natural Peanut Butter", "brand": "Store", "size": "16 oz",
         "category": "pantry", "price_cents": 299, "image_url": "/jar2.jpg", "image_credit": "test"},
    ]
    cheapest = final_intent(product="peanut butter", maxPrice=None, quantity=1, preferCheapest=True)
    assert [m.product.id for m in search_products(cheapest, catalog)[0]][:2] == ["jar2", "jar"]


def test_price_language_ranks_by_price_instead_of_becoming_a_hard_requirement():
    # Live regression: "Very cheap yogurt" set preferCheapest and also emitted
    # importantRequirements=["cheap"], which rejected every catalog product.
    cheap = final_intent(
        product="yogurt", maxPrice=None, quantity=1,
        preferCheapest=True, importantRequirements=["very cheap"],
    )
    matches, reason = search_products(cheap, CATALOG)
    assert reason is None
    assert [match.product.id for match in matches] == ["chobani", "fage"]

    # The commerce guard still works if the model forgets preferCheapest, and
    # it preserves actual properties stated alongside the price preference.
    affordable_nonfat = final_intent(
        product="yogurt", maxPrice=None, quantity=1,
        preferCheapest=False, importantRequirements=["affordable", "nonfat"],
    )
    matches, reason = search_products(affordable_nonfat, CATALOG)
    assert reason is None
    assert [match.product.id for match in matches] == ["chobani"]

    # "Low" by itself is not discarded: low sodium remains a real constraint.
    assert "low sodium" in search_products(
        final_intent(maxPrice=None, quantity=1, importantRequirements=["low sodium"]), CATALOG
    )[1]


def test_a_pack_size_can_be_matched_in_the_product_name():
    catalog = [{"id": "coke", "name": "Coca-Cola Mini Cans, 6 Pack", "brand": "Coca-Cola", "size": "45 fl oz",
                "category": "drinks", "price_cents": 499, "image_url": "/c.jpg", "image_credit": "test"}]
    matches, reason = search_products(final_intent(product="Coca-Cola", size="6 pack", maxPrice=None), catalog)
    assert reason is None and [m.product.id for m in matches] == ["coke"]


def test_two_heard_words_can_match_one_catalog_word():
    catalog = [{"id": "goldfish", "name": "Goldfish Cheddar Crackers", "brand": "Pepperidge Farm",
                "size": "2.65 oz", "category": "snacks", "price_cents": 149,
                "image_url": "/g.jpg", "image_credit": "test"}]
    matches, reason = search_products(final_intent(product="Gold fish crackers", maxPrice=None), catalog)
    assert reason is None and [m.product.id for m in matches] == ["goldfish"]


def test_no_match_says_which_constraint_ruled_everything_out():
    assert search_products(final_intent(product="headphones"), CATALOG)[1] == \
        "This store does not sell headphones."
    assert search_products(final_intent(brand="Yoplait"), CATALOG)[1] == \
        "This store does not carry Yoplait yogurt. It has Chobani Greek Yogurt, Nonfat Plain."
    assert search_products(final_intent(product="bananas", maxPrice=5), CATALOG)[1] == \
        "The lowest-priced match, Dole Organic Bananas, costs $5.98 for 2, over your $5.00 limit."


def test_search_never_guesses_wrong_merchant_or_currency():
    elsewhere, merchant_reason = search_products(
        final_intent(merchantPreference="Another Store"), CATALOG
    )
    assert elsewhere == [] and "merchant" in merchant_reason

    currency, currency_reason = search_products(final_intent(currency="EUR"), CATALOG)
    assert currency == [] and "USD" in currency_reason


def test_soft_preferences_are_disclosed_when_catalog_cannot_verify_them():
    matches, _ = search_products(
        final_intent(useCase="breakfast", optionalPreferences=["high protein"]), CATALOG
    )
    assert matches
    request = CommerceRequest(finalizedRequest=finalized(
        final_intent(useCase="breakfast", optionalPreferences=["high protein"])
    ))
    result = CommerceResult(
        status="no_matches", message="test", selectedProduct=None, rankedProducts=[],
        addedQuantity=0, items=[], quote=None,
        unverifiedPreferences=["use case: breakfast", "preference: high protein"],
    )
    assert result.unverifiedPreferences == ["use case: breakfast", "preference: high protein"]
    assert request.finalizedRequest.finalIntent.useCase == "breakfast"


def test_prepare_cart_preserves_lines_merges_quantity_and_uses_server_pricing(monkeypatch):
    monkeypatch.setattr(commerce_agent, "list_catalog", lambda: CATALOG)
    seen = {}

    def fake_price(lines):
        seen["lines"] = lines
        return {"lines": [], "subtotal_cents": 0, "tax_cents": 0, "shipping_cents": 0, "total_cents": 0}

    monkeypatch.setattr(commerce_agent, "price_cart", fake_price)
    request = CommerceRequest(
        finalizedRequest=finalized(),
        existingItems=[{"product_id": "bananas", "quantity": 1}, {"product_id": "chobani", "quantity": 3}],
    )
    result = prepare_commerce_cart(request)

    assert result.status == "cart_ready"
    assert result.selectedProduct.id == "chobani"
    assert result.addedQuantity == 2
    assert [(line.product_id, line.quantity) for line in result.items] == [("bananas", 1), ("chobani", 5)]
    assert seen["lines"] == [("bananas", 1), ("chobani", 5)]


def test_no_match_returns_existing_cart_unchanged(monkeypatch):
    monkeypatch.setattr(commerce_agent, "list_catalog", lambda: CATALOG)
    existing = [{"product_id": "bananas", "quantity": 2}]
    result = prepare_commerce_cart(CommerceRequest(
        finalizedRequest=finalized(final_intent(product="headphones")),
        existingItems=existing,
    ))
    assert result.status == "no_matches"
    assert result.selectedProduct is None
    assert [line.model_dump() for line in result.items] == existing
    assert result.quote is None


def test_commerce_route_returns_cart_ready_without_checkout(monkeypatch):
    client = TestClient(app)
    expected = CommerceResult(
        status="cart_ready", message="ready", selectedProduct=CATALOG[0],
        rankedProducts=[{"product": CATALOG[0], "score": 100}], addedQuantity=2,
        items=[{"product_id": "chobani", "quantity": 2}],
        quote={"total_cents": 1298}, unverifiedPreferences=[],
    )
    captured = {}

    def fake_prepare(body):
        captured["body"] = deepcopy(body.model_dump())
        return expected

    monkeypatch.setattr(agentic_shopping, "prepare_commerce_cart", fake_prepare)
    response = client.post("/agentic-shopping/commerce/prepare-cart", json={
        "finalizedRequest": finalized().model_dump(), "existingItems": [],
    })
    assert response.status_code == 200
    assert response.json()["status"] == "cart_ready"
    assert captured["body"]["finalizedRequest"]["finalIntent"]["quantity"] == 2
    assert "instruction_id" not in response.json()
    assert "session_id" not in response.json()
    paths = set(app.openapi()["paths"])
    assert "/agentic-shopping/commerce/prepare-cart" in paths
    assert "/checkout/confirm" in paths
    assert "/shopping/voice" in paths
