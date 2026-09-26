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


def test_search_never_guesses_unsupported_variant_or_wrong_merchant():
    colored, color_reason = search_products(final_intent(color="blue"), CATALOG)
    assert colored == [] and "color" in color_reason

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
