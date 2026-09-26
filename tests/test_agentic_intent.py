"""Feature 2: structured intent extraction for the additive OpenAI path."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from api import agentic_shopping, openai_intent
from api.main import app


def intent_payload():
    return {
        "intent": "shop",
        "product": {"value": "headphones", "confidence": "high", "sourceText": "headphones"},
        "brand": {"value": "Sony", "confidence": "medium", "sourceText": "sunny"},
        "maxPrice": {"value": 150, "currency": "USD", "confidence": "high", "sourceText": "one fifty"},
        "quantity": {"value": None, "confidence": "missing", "sourceText": None},
        "size": {"value": None, "confidence": "missing", "sourceText": None},
        "color": {"value": "black", "confidence": "high", "sourceText": "black"},
        "merchantPreference": {"value": None, "confidence": "missing", "sourceText": None},
        "useCase": {"value": "gym", "confidence": "high", "sourceText": "gym"},
        "importantRequirements": [],
        "optionalPreferences": [],
        "missingInformation": [],
        "ambiguities": [{
            "field": "brand", "kind": "possible_transcription_error", "heard": "sunny",
            "proposed": "Sony", "question": "Did you mean Sony?", "material": True,
        }],
    }


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", openai_intent.RESPONSES_URL)
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("provider detail", request=request, response=response)

    def json(self):
        return self.payload


def response_with(output):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": output}]}]}


def test_intent_uses_structured_output_and_preserves_uncertainty(monkeypatch):
    seen = {}
    monkeypatch.setattr(openai_intent, "OPENAI_API_KEY", "test-key")

    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse(response_with(json.dumps(intent_payload())))

    monkeypatch.setattr(openai_intent.httpx, "post", fake_post)
    result = openai_intent.extract_shopping_intent("I need black sunny headphones under one fifty for the gym")

    assert result.brand.value == "Sony"
    assert result.brand.sourceText == "sunny"
    assert result.brand.confidence == "medium"
    assert result.ambiguities[0].heard == "sunny"
    assert seen["url"] == openai_intent.RESPONSES_URL
    assert seen["json"]["model"] == "gpt-4.1-mini"
    assert seen["json"]["store"] is False
    assert seen["json"]["text"]["format"]["type"] == "json_schema"
    assert seen["json"]["text"]["format"]["strict"] is True


def test_intent_rejects_malformed_or_provider_responses(monkeypatch):
    monkeypatch.setattr(openai_intent, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_intent.httpx, "post", lambda *a, **k: FakeResponse(response_with("not json")))
    with pytest.raises(openai_intent.IntentUnavailable, match="cart were not changed"):
        openai_intent.extract_shopping_intent("headphones")

    monkeypatch.setattr(openai_intent.httpx, "post", lambda *a, **k: FakeResponse({}, 500))
    with pytest.raises(openai_intent.IntentUnavailable, match="cart were not changed") as error:
        openai_intent.extract_shopping_intent("headphones")
    assert "500" not in str(error.value)
    assert "provider detail" not in str(error.value)

    invalid = intent_payload()
    invalid["quantity"] = {"value": 0, "confidence": "high", "sourceText": "zero"}
    monkeypatch.setattr(
        openai_intent.httpx, "post", lambda *a, **k: FakeResponse(response_with(json.dumps(invalid)))
    )
    with pytest.raises(openai_intent.IntentUnavailable, match="cart were not changed"):
        openai_intent.extract_shopping_intent("zero headphones")


def test_intent_requires_server_key(monkeypatch):
    monkeypatch.setattr(openai_intent, "OPENAI_API_KEY", "")
    with pytest.raises(openai_intent.IntentUnavailable, match="OPENAI_API_KEY"):
        openai_intent.extract_shopping_intent("headphones")


def test_intent_route_retains_raw_transcript_and_does_not_mutate_cart(monkeypatch):
    client = TestClient(app)
    captured = {}
    before = client.get("/cart").json()

    def fake_extract(transcript):
        captured["transcript"] = transcript
        return openai_intent.ShoppingIntent.model_validate(intent_payload())

    monkeypatch.setattr(agentic_shopping, "extract_shopping_intent", fake_extract)
    raw = "  I need black sunny headphones under one fifty for the gym.\n"
    response = client.post("/agentic-shopping/intent", json={"transcript": raw})

    assert response.status_code == 200
    assert response.json()["rawTranscript"] == raw
    assert captured["transcript"] == raw
    assert response.json()["extractedIntent"]["ambiguities"][0]["proposed"] == "Sony"
    assert client.get("/cart").json() == before


def test_intent_route_rejects_empty_or_extra_input_and_keeps_existing_routes():
    client = TestClient(app)
    assert client.post("/agentic-shopping/intent", json={"transcript": "   "}).status_code == 422
    assert client.post(
        "/agentic-shopping/intent", json={"transcript": "headphones", "confirmed": True}
    ).status_code == 422
    paths = set(app.openapi()["paths"])
    assert {"/shopping/voice", "/shopping/text", "/agentic-shopping/transcribe", "/agentic-shopping/intent"} <= paths
