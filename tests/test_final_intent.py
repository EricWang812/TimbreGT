"""Feature 4: safe finalized structured shopping intent."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from api.ambiguity_resolution import ClarificationAnswer, apply_clarification_answer, build_clarification_state
from api.final_intent import FinalIntentError, finalize_shopping_intent
from api.main import app
from api.openai_intent import ShoppingIntent
from tests.test_agentic_intent import intent_payload


def extracted(payload=None) -> ShoppingIntent:
    return ShoppingIntent.model_validate(payload or intent_payload())


def answer_all(state, corrections=None):
    corrections = {"quantity": 1, **(corrections or {})}
    while state.pendingClarifications:
        question = state.pendingClarifications[0]
        answer = (
            ClarificationAnswer(field=question.field, action="correct", value=corrections[question.field])
            if question.proposed is None
            else ClarificationAnswer(field=question.field, action="confirm")
        )
        state = apply_clarification_answer(state, answer)
    return state


def confirmed_state():
    state = build_clarification_state("  black sunny headphones\n", extracted())
    return answer_all(state)


def test_final_intent_uses_confirmed_override_and_high_confidence_fields():
    state = confirmed_state()
    original = deepcopy(state.extractedIntent.model_dump())
    result = finalize_shopping_intent(state)

    assert result.rawTranscript == "  black sunny headphones\n"
    assert result.extractedIntent.model_dump() == original
    assert result.finalIntent.model_dump() == {
        "action": "shop",
        "product": "headphones",
        "brand": "Sony",
        "maxPrice": 150.0,
        "currency": "USD",
        "quantity": 1,
        "size": None,
        "color": "black",
        "merchantPreference": None,
        "useCase": "gym",
        "importantRequirements": [],
        "optionalPreferences": [],
    }


def test_finalization_refuses_pending_or_nonshopping_state():
    pending = build_clarification_state("sunny headphones", extracted())
    with pytest.raises(FinalIntentError, match="Resolve the product"):
        finalize_shopping_intent(pending)

    payload = intent_payload()
    payload["intent"] = "not_shopping"
    payload["ambiguities"] = []
    with pytest.raises(FinalIntentError, match="not confirmed"):
        finalize_shopping_intent(build_clarification_state("hello", extracted(payload)))


def test_correction_changes_only_final_field_and_retains_source_history():
    state = build_clarification_state("sunny headphones", extracted())
    rejected = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="reject"))
    corrected = apply_clarification_answer(
        rejected, ClarificationAnswer(field="brand", action="correct", value="Bose")
    )
    result = finalize_shopping_intent(answer_all(corrected))

    assert result.finalIntent.brand == "Bose"
    assert result.finalIntent.product == "headphones"
    assert result.extractedIntent.brand.value == "Sony"
    assert result.extractedIntent.brand.sourceText == "sunny"
    assert result.clarificationAnswers["brand"].value == "Bose"


def test_only_missing_mandatory_fields_are_clarified_and_numeric_answers_are_typed():
    payload = intent_payload()
    payload["ambiguities"] = []
    payload["size"] = {"value": None, "confidence": "missing", "sourceText": None}
    payload["quantity"] = {"value": None, "confidence": "missing", "sourceText": None}
    payload["missingInformation"] = ["size", "quantity"]
    state = build_clarification_state("two shirts", extracted(payload))
    fields = {item.field for item in state.pendingClarifications}
    assert "quantity" in fields
    assert "size" not in fields

    complete = answer_all(state, {"quantity": "2"})
    result = finalize_shopping_intent(complete)
    assert result.finalIntent.size is None
    assert result.finalIntent.quantity == 2


def test_unconfirmed_values_are_not_promoted_to_final_facts():
    payload = intent_payload()
    payload["ambiguities"][0]["material"] = False
    state = build_clarification_state("sunny headphones", extracted(payload))

    assert "brand" in {item.field for item in state.pendingClarifications}
    with pytest.raises(FinalIntentError, match="Resolve the product"):
        finalize_shopping_intent(state)


def test_finalize_route_recomputes_state_and_never_changes_cart():
    client = TestClient(app)
    state = confirmed_state().model_dump()
    state["complete"] = False
    state["resolvedValues"] = {"brand": "forged"}
    before = client.get("/cart").json()

    response = client.post("/agentic-shopping/finalize", json=state)
    assert response.status_code == 200
    assert response.json()["finalIntent"]["brand"] == "Sony"
    assert response.json()["rawTranscript"] == "  black sunny headphones\n"
    assert client.get("/cart").json() == before

    pending = build_clarification_state("sunny headphones", extracted()).model_dump()
    blocked = client.post("/agentic-shopping/finalize", json=pending)
    assert blocked.status_code == 409

    paths = set(app.openapi()["paths"])
    assert "/agentic-shopping/finalize" in paths
    assert "/shopping/voice" in paths
