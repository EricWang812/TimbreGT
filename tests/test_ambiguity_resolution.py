"""Clarification policy: ask only when a wrong guess changes what is bought."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from api.ambiguity_resolution import (
    ClarificationAnswer,
    apply_clarification_answer,
    build_clarification_state,
    closest_store_brand,
    store_vocabulary,
)
from api.main import app
from api.openai_intent import ShoppingIntent
from tests.test_agentic_intent import intent_payload, store  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("store")

MISSING = {"value": None, "confidence": "missing", "sourceText": None}


def intent(**changes) -> ShoppingIntent:
    payload = intent_payload()
    payload.update(changes)
    return ShoppingIntent.model_validate(payload)


def clear_banana(**changes) -> ShoppingIntent:
    payload = intent_payload()
    payload.update(
        product={"value": "banana", "confidence": "high", "sourceText": "banana"},
        brand=MISSING, color=MISSING, useCase=MISSING, quantity=MISSING,
        maxPrice={"value": 5, "currency": "USD", "confidence": "high", "sourceText": "five dollars"},
        ambiguities=[],
    )
    payload.update(changes)
    return ShoppingIntent.model_validate(payload)


def boys_headphones() -> ShoppingIntent:
    """The live failure: "boys" filed as a use case and a preference, never as Bose."""
    payload = intent_payload()
    payload.update(
        brand=MISSING, color=MISSING, maxPrice={
            "value": 400, "currency": "USD", "confidence": "high", "sourceText": "$400"},
        useCase={"value": "boys", "confidence": "medium", "sourceText": "boys"},
        optionalPreferences=["boys"],
        ambiguities=[{
            "field": "useCase", "kind": "ambiguous", "heard": "boys", "proposed": "boys",
            "question": "Should I use use case boys?", "material": True,
        }],
    )
    return ShoppingIntent.model_validate(payload)


def test_a_clear_request_needs_no_questions():
    state = build_clarification_state("one banana, at most five dollars", clear_banana(
        quantity={"value": 1, "confidence": "high", "sourceText": "one"}))

    assert state.pendingClarifications == []
    assert state.complete
    assert state.acceptedValues == {"product": "banana", "quantity": 1, "maxPrice": 5.0}
    assert state.resolvedValues == {}
    assert state.assumptions == []


def test_an_unsure_quantity_of_one_or_a_value_marked_missing_is_the_default():
    # Live: "some ice cream" gave quantity 1 at medium, and "coffee under three
    # dollars" gave quantity 1 marked missing. Neither is worth a question.
    unsure = build_clarification_state("some bananas", clear_banana(
        quantity={"value": 1, "confidence": "medium", "sourceText": "some"}))
    marked_missing = build_clarification_state("bananas", clear_banana(
        quantity={"value": 1, "confidence": "missing", "sourceText": None}))
    for state in (unsure, marked_missing):
        assert state.complete and state.acceptedValues["quantity"] == 1
        assert state.assumptions == ["Quantity 1, since you did not say how many."]

    two = build_clarification_state("to bananas", clear_banana(
        quantity={"value": 2, "confidence": "medium", "sourceText": "to"}))
    assert [q.question for q in two.pendingClarifications] == ["Did you want 2?"]


def test_unstated_quantity_and_budget_become_disclosed_defaults():
    state = build_clarification_state("bananas", clear_banana(maxPrice={
        "value": None, "currency": None, "confidence": "missing", "sourceText": None}))

    assert state.complete
    assert state.acceptedValues == {"product": "banana", "quantity": 1}
    assert state.assumptions == [
        "Quantity 1, since you did not say how many.",
        "No price limit, since you did not name one.",
    ]


def test_only_the_uncertain_value_is_asked_and_originals_are_preserved():
    raw = "  black sunny headphones\n"
    extracted = intent()
    before = deepcopy(extracted.model_dump())
    state = build_clarification_state(raw, extracted)

    assert [q.field for q in state.pendingClarifications] == ["brand"]
    assert [o.label for o in state.pendingClarifications[0].options] == ["Yes", "No"]
    result = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="confirm"))
    assert result.complete
    assert result.rawTranscript == raw
    assert result.extractedIntent.model_dump() == before
    assert result.resolvedValues == {"brand": "Sony"}
    assert result.acceptedValues == {
        "product": "headphones", "color": "black", "useCase": "gym", "quantity": 1, "maxPrice": 150.0,
    }


def test_rejection_asks_for_that_field_only_then_accepts_correction():
    state = build_clarification_state("sunny headphones", intent())
    rejected = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="reject"))

    assert [q.question for q in rejected.pendingClarifications] == ["What brand did you mean?"]
    assert rejected.pendingClarifications[0].options == []
    corrected = apply_clarification_answer(
        rejected, ClarificationAnswer(field="brand", action="correct", value="Bose")
    )
    assert corrected.resolvedValues == {"brand": "Bose"}
    assert corrected.clarificationAnswers["brand"].value == "Bose"
    assert corrected.complete


def test_heard_word_is_proposed_as_a_store_brand_once_and_set_aside():
    state = build_clarification_state("I want boys headphones at $400", boys_headphones())

    # One span of words, one question, and the brand is one the store carries.
    assert len(state.pendingClarifications) == 1
    question = state.pendingClarifications[0]
    assert (question.field, question.heard, question.proposed) == ("brand", "boys", "Bose")
    assert question.question == 'I heard "boys". Did you mean Bose?'
    assert "useCase" not in state.acceptedValues
    assert state.extractedIntent.useCase.value == "boys"   # the model's reading is kept as evidence

    confirmed = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="confirm"))
    assert confirmed.complete
    assert confirmed.resolvedValues == {"brand": "Bose"}
    assert {(s.field, s.text) for s in confirmed.setAside} == {
        ("useCase", "boys"), ("optionalPreferences", "boys"),
    }


def test_declining_a_brand_repair_keeps_the_original_words_and_asks_nothing_more():
    state = build_clarification_state("I want boys headphones", boys_headphones())
    declined = apply_clarification_answer(state, ClarificationAnswer(field="brand", action="reject"))

    assert declined.complete
    assert declined.resolvedValues == {}
    assert declined.setAside == []


def test_a_proposed_brand_must_be_one_the_store_carries():
    vocabulary = store_vocabulary()
    assert closest_store_brand("boys", vocabulary) == "Bose"
    assert closest_store_brand("sunny", vocabulary) == "Sony"
    assert closest_store_brand("for the gym", vocabulary) is None
    assert closest_store_brand("organic", vocabulary) is None   # describes a product
    assert closest_store_brand("Chobani", vocabulary) is None   # the brand itself, not a mishearing

    payload = intent_payload()
    payload["ambiguities"][0].update(heard="bows", proposed="Boss")   # not sold here
    state = build_clarification_state("bows headphones", ShoppingIntent.model_validate(payload))
    assert state.pendingClarifications[0].proposed == "Bose"


def test_a_store_brand_the_speaker_never_said_is_neither_asked_nor_used():
    # Live failure: "two OJs" came back as brand Simply Orange, then was asked about.
    payload = intent_payload()
    payload.update(
        product={"value": "yogurt", "confidence": "high", "sourceText": "yogurts"},
        brand={"value": "Chobani", "confidence": "medium", "sourceText": "yogurts"},
        color=MISSING, useCase=MISSING,
        ambiguities=[{"field": "brand", "kind": "ambiguous", "heard": "yogurts", "proposed": "Chobani",
                      "question": "Did you mean 'Chobani' brand for 'yogurts'?", "material": True}],
    )
    state = build_clarification_state("two yogurts", ShoppingIntent.model_validate(payload))
    assert state.pendingClarifications == []
    assert "brand" not in state.acceptedValues
    assert "brand" in state.ignoredFields   # the panel does not show it as understood

    payload["brand"] = {"value": "Chobani", "confidence": "high", "sourceText": "chobani"}
    payload["ambiguities"] = []
    said = build_clarification_state("chobani yogurt", ShoppingIntent.model_validate(payload))
    assert said.acceptedValues["brand"] == "Chobani"


def test_an_unsure_detail_the_speaker_never_said_is_dropped_not_asked():
    # Live: "two cokes" came back with size "6 Pack" at medium confidence.
    payload = intent_payload()
    payload.update(brand=MISSING, ambiguities=[], color=MISSING,
                   size={"value": "6 Pack", "confidence": "medium", "sourceText": "6 Pack"})
    state = build_clarification_state("two cokes please", ShoppingIntent.model_validate(payload))
    assert state.pendingClarifications == [] and "size" not in state.acceptedValues

    said = build_clarification_state("two six pack cokes", ShoppingIntent.model_validate(
        {**payload, "size": {"value": "six pack", "confidence": "medium", "sourceText": "six pack"}}))
    assert [q.field for q in said.pendingClarifications] == ["size"]


def test_missing_product_gets_one_open_question():
    payload = intent_payload()
    payload.update(product=MISSING, ambiguities=[], brand=MISSING, missingInformation=["product"])
    state = build_clarification_state("I need something for the gym", ShoppingIntent.model_validate(payload))

    assert [(q.field, q.question) for q in state.pendingClarifications] == [
        ("product", "What would you like to buy?")
    ]
    corrected = apply_clarification_answer(
        state, ClarificationAnswer(field="product", action="correct", value="headphones")
    )
    assert corrected.resolvedValues == {"product": "headphones"}
    assert corrected.complete


def test_non_shopping_speech_asks_nothing():
    state = build_clarification_state("hello there", intent(intent="not_shopping"))
    assert state.pendingClarifications == []


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
    assert valid.json()["complete"] is True
    assert client.get("/cart").json() == before

    paths = set(app.openapi()["paths"])
    assert "/shopping/voice" in paths
    assert "/agentic-shopping/clarifications/answer" in paths
