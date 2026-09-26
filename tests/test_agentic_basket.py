"""A whole spoken basket: several named items, meals, and one shared budget."""
import json

import pytest
from fastapi.testclient import TestClient

from api import basket, openai_intent
from api.basket import BasketAnswer, BasketPrepareRequest, apply_basket_answer, build_basket_state, prepare_basket
from api.commerce_agent import CommerceError
from api.main import app
from api.openai_intent import BasketIntent
from tests.test_agentic_intent import FakeResponse, intent_payload, response_with, store  # noqa: F401
from tests.test_ambiguity_resolution import MISSING

pytestmark = pytest.mark.usefixtures("store")


def product(pid, name, brand, price, category="pantry", size="1 ct"):
    return {"id": pid, "name": name, "brand": brand, "size": size, "category": category,
            "price_cents": price, "image_url": f"/{pid}.jpg", "image_credit": "test"}


SHELF = [
    product("tuna", "Albacore Tuna", "Wild Planet", 449, "seafood"),
    product("bread", "Farmhouse Sourdough Bread", "Pepperidge Farm", 479, "bakery"),
    product("coke", "Coca-Cola Mini Cans, 6 Pack", "Coca-Cola", 499, "drinks"),
    product("yogurt", "Vanilla Greek Yogurt", "Chobani", 149, "dairy"),
]


@pytest.fixture(autouse=True)
def shelf(monkeypatch):
    monkeypatch.setattr(basket, "list_catalog", lambda: SHELF)
    monkeypatch.setattr(basket, "price_cart", lambda lines: {"lines": lines, "total_cents": sum(
        {p["id"]: p["price_cents"] for p in SHELF}[pid] * qty for pid, qty in lines)})


def item(name, quantity=None, mode="exact", price=None, brand=None, said="same"):
    payload = intent_payload()
    payload.update(
        product={"value": name, "confidence": "high", "sourceText": name if said == "same" else said},
        brand=brand or MISSING, color=MISSING, useCase=MISSING, ambiguities=[],
        quantity={"value": quantity, "mode": mode, "confidence": "high" if quantity else "missing",
                  "sourceText": str(quantity) if quantity else None},
        maxPrice={"value": price, "currency": "USD" if price else None,
                  "confidence": "high" if price else "missing", "sourceText": f"${price}" if price else None},
    )
    return payload


def ingredient(need, pid, quantity=1, reason="for the dish"):
    return {"need": need, "productId": pid, "quantity": quantity, "reason": reason}


def request(items=(), meals=(), total=None, intent="shop") -> BasketIntent:
    return BasketIntent.model_validate({
        "intent": intent, "items": list(items), "meals": list(meals),
        "totalBudget": {"value": total, "currency": "USD" if total else None, "per": "total",
                        "confidence": "high" if total else "missing", "sourceText": None},
    })


def spoken(req) -> str:
    """A transcript in which the shopper said every named item."""
    return " and ".join(i.product.sourceText for i in req.items if i.product.sourceText) or "raw"


def prepare(req, existing=(), skip=()):
    state = build_basket_state(spoken(req), req)
    return prepare_basket(BasketPrepareRequest(state=state, existingItems=list(existing), skip=list(skip)))


def test_several_named_items_go_straight_to_the_cart():
    result = prepare(request([item("Coca-Cola", 2), item("greek yogurt", 3)]),
                     existing=[{"product_id": "tuna", "quantity": 1}])

    assert result.status == "cart_ready"
    assert [(line.product.id, line.quantity) for line in result.lines] == [("coke", 2), ("yogurt", 3)]
    assert [(line.product_id, line.quantity) for line in result.items] == [("tuna", 1), ("coke", 2), ("yogurt", 3)]
    assert result.message == "Added 2 × Coca-Cola Mini Cans, 6 Pack and 3 × Chobani Vanilla Greek Yogurt to your cart."
    # Said once, not once per item.
    assert result.assumptions == ["No price limit, since you did not name one."]
    two_limits = build_basket_state("raw", request([item("Coca-Cola", 2), item("greek yogurt", 3, price=5)]))
    assert two_limits.assumptions == ["Coca-Cola: No price limit, since you did not name one."]


def test_a_meal_is_checked_against_the_catalog_and_shown_before_adding():
    meal = {"goal": "tuna salad", "servings": 2, "cannotVerify": ["gluten-free"], "ingredients": [
        ingredient("tuna", "tuna", 2, "the main ingredient"),
        ingredient("bread", "bread", 1, "to serve it on"),
        ingredient("mayonnaise", None),
        ingredient("celery", "made-up-id"),          # a hallucinated id is never trusted
    ]}
    result = prepare(request(meals=[meal]))

    assert result.status == "needs_confirmation"
    assert [(line.product.id, line.quantity, line.note) for line in result.lines] == [
        ("tuna", 2, "the main ingredient"), ("bread", 1, "to serve it on")]
    assert result.notCarried == ["mayonnaise (tuna salad)", "celery (tuna salad)"]
    assert result.unverified == ["gluten-free (tuna salad)"]
    assert result.message.startswith("Timbre picked 2 × Wild Planet Albacore Tuna and 1 × ")

    without_bread = prepare(request(meals=[meal]), skip=[1])
    assert [line.skipped for line in without_bread.lines] == [False, True]
    assert [(line.product_id, line.quantity) for line in without_bread.items] == [("tuna", 2)]


def test_a_meal_and_named_items_together_and_ingredients_are_not_diet_claims():
    # Live failure: "stuff for tuna salad, and two cokes" dropped the cokes.
    meal = {"goal": "tuna salad", "servings": 2, "cannotVerify": ["mayonnaise", "no nuts"], "ingredients": [
        ingredient("tuna", "tuna"), ingredient("mayonnaise", None)]}
    result = prepare(request([item("Coca-Cola", 2)], meals=[meal]))
    assert [(line.source, line.product.id) for line in result.lines] == [("request", "coke"), ("meal", "tuna")]
    assert result.unverified == ["no nuts (tuna salad)"]      # "mayonnaise" is an ingredient, not a diet need


def test_an_item_the_shopper_never_said_is_reviewed_not_added():
    # Live: the model filed a dish's ingredients as items; "bread" was never said.
    req = request([item("Coca-Cola", 2, said="cokes"), item("bread", 1, said=None)])
    state = build_basket_state("stuff for tuna salad and two cokes", req)
    result = prepare_basket(BasketPrepareRequest(state=state))
    assert result.status == "needs_confirmation"
    assert [(line.source, line.note) for line in result.lines] == [("request", ""), ("meal", "Timbre chose this.")]


def test_a_vague_request_asks_for_items_or_a_dish():
    with pytest.raises(CommerceError, match="what I need for tuna salad"):
        prepare(request(intent="unclear"))


def test_one_budget_is_shared_and_as_many_as_fit_gets_what_is_left():
    # "two cokes and as much yogurt as fits, all under $20"
    result = prepare(request([item("Coca-Cola", 2), item("greek yogurt", mode="fill_budget")], total=20))

    assert result.status == "cart_ready"
    assert [(line.product.id, line.quantity) for line in result.lines] == [("coke", 2), ("yogurt", 6)]
    assert result.lines[1].note == "As many as fit in $10.02."   # $20.00 - 2 x $4.99
    assert result.assumptions == []                               # the basket budget covers both


def test_a_fill_item_with_a_basket_budget_asks_nothing():
    state = build_basket_state("raw", request([item("greek yogurt", mode="fill_budget")], total=5))
    assert state.complete


def test_going_over_the_basket_budget_is_shown_not_silently_trimmed():
    result = prepare(request([item("Coca-Cola", 2), item("Albacore Tuna", 2)], total=15))
    assert result.status == "needs_confirmation"
    assert result.message.endswith("These come to $18.96, over your $15.00 limit. Remove something before adding.")


def test_questions_are_per_item_and_answers_touch_only_that_item():
    uncertain = intent_payload()      # "sunny" heard, Sony proposed at medium confidence
    req = request([item("greek yogurt", 2), uncertain])
    state = build_basket_state("raw", req)
    assert [(q.item, q.itemLabel, q.field) for q in state.pendingClarifications] == [(1, "headphones", "brand")]

    with pytest.raises(ValueError):
        apply_basket_answer(state, BasketAnswer(item=0, field="brand", action="confirm"))
    done = apply_basket_answer(state, BasketAnswer(item=1, field="brand", action="confirm"))
    assert done.complete
    assert done.items[1].resolvedValues == {"brand": "Sony"}
    assert done.items[0].clarificationAnswers == {}


def test_nothing_found_or_not_shopping_leaves_the_cart_alone():
    existing = [{"product_id": "tuna", "quantity": 1}]
    none = prepare(request([item("headphones", 1)]), existing=existing)
    assert none.status == "no_matches"
    assert none.message == "This store does not sell headphones."
    assert [line.model_dump() for line in none.items] == existing

    with pytest.raises(CommerceError, match="did not sound like a shopping request"):
        prepare(request(intent="not_shopping"))


def test_basket_extraction_sends_catalog_ids_and_a_strict_schema(monkeypatch):
    seen = {}
    monkeypatch.setattr(openai_intent, "OPENAI_API_KEY", "test-key")
    payload = {"intent": "shop", "items": [item("Coca-Cola", 2)], "meals": [], "totalBudget": {
        "value": None, "currency": None, "per": "total", "confidence": "missing", "sourceText": None}}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse(response_with(json.dumps(payload)))

    monkeypatch.setattr(openai_intent.httpx, "post", fake_post)
    result = openai_intent.extract_basket_intent("two cokes")
    assert result.items[0].quantity.value == 2
    sent = seen["json"]
    assert sent["text"]["format"]["name"] == "shopping_basket"
    assert "- bose-qc | Bose | QuietComfort Headphones" in sent["instructions"]
    assert "stuff to\nmake tuna salad" in sent["instructions"]
    assert '"default"' not in json.dumps(sent["text"]["format"]["schema"])


def test_basket_routes_never_change_the_server_cart():
    client = TestClient(app)
    before = client.get("/cart").json()
    req = request([item("Coca-Cola", 2)]).model_dump()
    state = client.post("/agentic-shopping/basket/clarifications",
                        json={"rawTranscript": "two Coca-Cola", "extractedRequest": req})
    assert state.status_code == 200 and state.json()["complete"] is True

    wrong = client.post("/agentic-shopping/basket/clarifications/answer", json={
        "state": state.json(), "answer": {"item": 3, "field": "brand", "action": "confirm"}})
    assert wrong.status_code == 422

    prepared = client.post("/agentic-shopping/basket/prepare", json={"state": state.json()})
    assert prepared.status_code == 200 and prepared.json()["status"] == "cart_ready"
    assert client.get("/cart").json() == before
    paths = set(app.openapi()["paths"])
    assert {"/agentic-shopping/basket/prepare", "/agentic-shopping/intent", "/shopping/voice"} <= paths
