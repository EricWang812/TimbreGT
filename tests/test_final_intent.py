"""Finalized structured shopping intent: only confirmed, clearly heard, or disclosed facts."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from api.ambiguity_resolution import ClarificationAnswer, apply_clarification_answer, build_clarification_state
from api.final_intent import FinalIntentError, finalize_shopping_intent, normalize_currency
from api.main import app
from api.openai_intent import ShoppingIntent
from tests.test_agentic_intent import intent_payload, store  # noqa: F401  (fixture)
from tests.test_ambiguity_resolution import MISSING, boys_headphones

pytestmark = pytest.mark.usefixtures("store")


def extracted(payload=None) -> ShoppingIntent:
    return ShoppingIntent.model_validate(payload or intent_payload())


def confirmed_state():
    state = build_clarification_state("  black sunny headphones\n", extracted())
    return apply_clarification_answer(state, ClarificationAnswer(field="brand", action="confirm"))


def test_final_intent_combines_confirmed_and_clearly_heard_fields():
    state = confirmed_state()
    original = deepcopy(state.extractedIntent.model_dump())
    result = finalize_shopping_intent(state)

    assert result.rawTranscript == "  black sunny headphones\n"
    assert result.extractedIntent.model_dump() == original
    assert result.assumptions == ["Quantity 1, since you did not say how many."]
    assert result.finalIntent.model_dump() == {
        "action": "shop",
        "product": "headphones",
        "brand": "Sony",
        "maxPrice": 150.0,
        "pricePer": "total",
        "currency": "USD",
        "quantity": 1,
        "quantityMode": "exact",
        "preferCheapest": False,
        "size": None,
        "color": "black",
        "merchantPreference": None,
        "useCase": "gym",
        "importantRequirements": [],
        "optionalPreferences": [],
    }


def test_finalization_refuses_pending_or_nonshopping_state():
    pending = build_clarification_state("sunny headphones", extracted())
    with pytest.raises(FinalIntentError, match="Resolve the brand"):
        finalize_shopping_intent(pending)

    payload = intent_payload()
    payload["intent"] = "not_shopping"
    payload["ambiguities"] = []
    with pytest.raises(FinalIntentError, match="did not sound like a shopping request"):
        finalize_shopping_intent(build_clarification_state("hello", extracted(payload)))


def test_unclear_speech_becomes_shopping_only_after_the_product_is_confirmed():
    payload = intent_payload()
    payload.update(intent="unclear", brand=MISSING, ambiguities=[])
    state = build_clarification_state("uh headphones maybe", extracted(payload))
    assert [q.field for q in state.pendingClarifications] == ["product"]

    confirmed = apply_clarification_answer(state, ClarificationAnswer(field="product", action="confirm"))
    assert finalize_shopping_intent(confirmed).finalIntent.product == "headphones"


def test_correction_changes_only_final_field_and_retains_source_history():
    state = build_clarification_state("sunny headphones", extracted())
    rejected = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="reject"))
    corrected = apply_clarification_answer(
        rejected, ClarificationAnswer(field="brand", action="correct", value="Bose")
    )
    result = finalize_shopping_intent(corrected)

    assert result.finalIntent.brand == "Bose"
    assert result.finalIntent.product == "headphones"
    assert result.extractedIntent.brand.value == "Sony"
    assert result.extractedIntent.brand.sourceText == "sunny"
    assert result.clarificationAnswers["brand"].value == "Bose"


def test_brand_repair_drops_the_same_words_from_other_fields():
    state = build_clarification_state("boys headphones", boys_headphones())
    confirmed = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="confirm"))
    final = finalize_shopping_intent(confirmed).finalIntent
    assert (final.brand, final.useCase, final.optionalPreferences) == ("Bose", None, [])

    declined = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="reject"))
    final = finalize_shopping_intent(declined).finalIntent
    assert final.brand is None
    assert final.optionalPreferences == ["boys"]


def test_unstated_quantity_and_budget_finalize_as_one_and_no_limit():
    payload = intent_payload()
    payload.update(brand=MISSING, ambiguities=[], quantity=MISSING, maxPrice={
        "value": None, "currency": None, "confidence": "missing", "sourceText": None})
    result = finalize_shopping_intent(build_clarification_state("headphones", extracted(payload)))

    assert result.finalIntent.quantity == 1
    assert result.finalIntent.maxPrice is None
    assert result.finalIntent.currency is None
    assert len(result.assumptions) == 2


def test_numeric_corrections_are_typed_and_spoken_currency_is_usd():
    payload = intent_payload()
    payload.update(brand=MISSING, ambiguities=[],
                   quantity={"value": 2, "confidence": "low", "sourceText": "to"},
                   maxPrice={"value": 150, "currency": "dollars", "confidence": "high", "sourceText": "150"})
    state = build_clarification_state("to headphones", extracted(payload))
    assert [q.field for q in state.pendingClarifications] == ["quantity"]
    rejected = apply_clarification_answer(state, ClarificationAnswer(field="quantity", action="reject"))
    corrected = apply_clarification_answer(
        rejected, ClarificationAnswer(field="quantity", action="correct", value="3"))
    final = finalize_shopping_intent(corrected).finalIntent

    assert final.quantity == 3
    assert final.currency == "USD"
    assert normalize_currency("$") == "USD" and normalize_currency("eur") == "EUR"


def test_as_many_as_fit_needs_only_a_budget():
    payload = intent_payload()
    payload.update(brand=MISSING, ambiguities=[], preferCheapest=True,
                   quantity={"value": None, "mode": "fill_budget", "confidence": "high",
                             "sourceText": "as much as I can"},
                   maxPrice={"value": 10, "currency": "USD", "confidence": "high", "sourceText": "under 10 bucks"})
    state = build_clarification_state("as much yogurt as I can under 10 bucks", extracted(payload))
    assert state.pendingClarifications == [] and state.assumptions == []
    final = finalize_shopping_intent(state).finalIntent
    assert (final.quantityMode, final.quantity, final.maxPrice, final.preferCheapest) == (
        "fill_budget", None, 10.0, True)

    payload["maxPrice"] = {"value": None, "currency": None, "confidence": "missing", "sourceText": None}
    no_budget = build_clarification_state("as much yogurt as I can", extracted(payload))
    assert [q.question for q in no_budget.pendingClarifications] == ["How much do you want to spend in total?"]
    answered = apply_clarification_answer(
        no_budget, ClarificationAnswer(field="maxPrice", action="correct", value="$12"))
    assert finalize_shopping_intent(answered).finalIntent.maxPrice == 12.0


def test_a_per_item_limit_is_kept_as_per_item():
    payload = intent_payload()
    payload.update(brand=MISSING, ambiguities=[],
                   maxPrice={"value": 2, "currency": "USD", "per": "each", "confidence": "high",
                             "sourceText": "under $2 each"})
    final = finalize_shopping_intent(build_clarification_state("yogurt under $2 each", extracted(payload))).finalIntent
    assert (final.maxPrice, final.pricePer) == (2.0, "each")


def test_unconfirmed_values_are_not_promoted_to_final_facts():
    payload = intent_payload()
    payload["ambiguities"][0]["material"] = False
    state = build_clarification_state("sunny headphones", extracted(payload))

    # The brand is still medium confidence, so it is still asked about.
    assert "brand" in {item.field for item in state.pendingClarifications}
    with pytest.raises(FinalIntentError, match="Resolve the brand"):
        finalize_shopping_intent(state)


def test_finalize_route_recomputes_state_and_never_changes_cart():
    client = TestClient(app)
    state = confirmed_state().model_dump()
    state["complete"] = False
    state["resolvedValues"] = {"brand": "forged"}
    state["acceptedValues"] = {"product": "forged", "quantity": 99}
    before = client.get("/cart").json()

    response = client.post("/agentic-shopping/finalize", json=state)
    assert response.status_code == 200
    assert response.json()["finalIntent"]["brand"] == "Sony"
    assert response.json()["finalIntent"]["product"] == "headphones"
    assert response.json()["finalIntent"]["quantity"] == 1
    assert response.json()["rawTranscript"] == "  black sunny headphones\n"
    assert client.get("/cart").json() == before

    pending = build_clarification_state("sunny headphones", extracted()).model_dump()
    blocked = client.post("/agentic-shopping/finalize", json=pending)
    assert blocked.status_code == 409

    paths = set(app.openapi()["paths"])
    assert "/agentic-shopping/finalize" in paths
    assert "/shopping/voice" in paths
