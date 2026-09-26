"""Feature 3: targeted, field-level ambiguity resolution."""
from copy import deepcopy

from fastapi.testclient import TestClient

from api.ambiguity_resolution import (
    ClarificationAnswer,
    apply_clarification_answer,
    build_clarification_state,
)
from api.main import app
from api.openai_intent import ShoppingIntent
from tests.test_agentic_intent import intent_payload


def intent(**changes) -> ShoppingIntent:
    payload = intent_payload()
    payload.update(changes)
    return ShoppingIntent.model_validate(payload)


def test_every_supplied_request_aspect_becomes_a_targeted_question():
    payload = intent_payload()
    payload["quantity"] = {"value": 2, "confidence": "high", "sourceText": "two"}
    payload["size"] = {"value": "medium", "confidence": "high", "sourceText": "medium"}
    payload["merchantPreference"] = {
        "value": "Seaside Market", "confidence": "high", "sourceText": "Seaside Market",
    }
    payload["importantRequirements"] = ["water resistant"]
    payload["optionalPreferences"] = ["foldable"]
    state = build_clarification_state("raw transcript", ShoppingIntent.model_validate(payload))

    assert [question.field for question in state.pendingClarifications] == [
        "product", "brand", "maxPrice", "quantity", "size", "color",
        "merchantPreference", "useCase", "importantRequirements", "optionalPreferences",
    ]
    assert all(
        [option.label for option in question.options] == ["Yes", "No"]
        for question in state.pendingClarifications
    )
    assert not state.complete


def test_confirmation_resolves_only_that_field_and_preserves_originals():
    raw = "  black sunny headphones\n"
    extracted = intent()
    before = deepcopy(extracted.model_dump())
    state = build_clarification_state(raw, extracted)
    result = apply_clarification_answer(
        state, ClarificationAnswer(field="brand", action="confirm")
    )

    assert result.rawTranscript == raw
    assert result.extractedIntent.model_dump() == before
    assert result.extractedIntent.brand.sourceText == "sunny"
    assert result.resolvedValues == {"brand": "Sony"}
    assert [item.field for item in result.pendingClarifications] == [
        "product", "maxPrice", "quantity", "color", "useCase"
    ]
    assert not result.complete


def test_rejection_asks_for_field_only_then_accepts_correction():
    state = build_clarification_state("sunny headphones", intent())
    rejected = apply_clarification_answer(
        state, ClarificationAnswer(field="brand", action="reject")
    )

    assert rejected.rawTranscript == "sunny headphones"
    brand_question = next(item for item in rejected.pendingClarifications if item.field == "brand")
    assert brand_question.question == "What brand did you mean?"
    assert brand_question.options == []
    assert rejected.resolvedValues == {}

    corrected = apply_clarification_answer(
        rejected, ClarificationAnswer(field="brand", action="correct", value="Bose")
    )
    assert corrected.resolvedValues == {"brand": "Bose"}
    assert corrected.clarificationAnswers["brand"].value == "Bose"
    assert not corrected.complete


def test_missing_product_gets_one_necessary_open_question():
    payload = intent_payload()
    payload["product"] = {"value": None, "confidence": "missing", "sourceText": None}
    payload["ambiguities"] = []
    payload["missingInformation"] = ["product"]
    state = build_clarification_state("I need something for the gym", ShoppingIntent.model_validate(payload))

    fields = {item.field for item in state.pendingClarifications}
    assert {"product", "maxPrice", "quantity"} <= fields
    assert "size" not in fields
    assert "merchantPreference" not in fields
    product_question = state.pendingClarifications[0]
    assert product_question.field == "product"
    assert product_question.question == "What product did you mean?"

    corrected = apply_clarification_answer(
        state, ClarificationAnswer(field="product", action="correct", value="headphones")
    )
    assert corrected.resolvedValues == {"product": "headphones"}
    assert not corrected.complete


def test_routes_reject_invalid_answers_and_never_change_cart():
    client = TestClient(app)
    before = client.get("/cart").json()
    start = client.post("/agentic-shopping/clarifications", json={
        "rawTranscript": "sunny headphones",
        "extractedIntent": intent_payload(),
    })
    assert start.status_code == 200

    state = start.json()
    invalid = client.post("/agentic-shopping/clarifications/answer", json={
        "state": state,
        "answer": {"field": "size", "action": "confirm"},
    })
    assert invalid.status_code == 422

    valid = client.post("/agentic-shopping/clarifications/answer", json={
        "state": state,
        "answer": {"field": "brand", "action": "confirm"},
    })
    assert valid.status_code == 200
    assert valid.json()["resolvedValues"] == {"brand": "Sony"}
    assert client.get("/cart").json() == before

    paths = set(app.openapi()["paths"])
    assert "/shopping/voice" in paths
    assert "/agentic-shopping/clarifications/answer" in paths
