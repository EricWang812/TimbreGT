"""Feature 1: OpenAI transcription without touching the Whisper shopping path."""
import io

import httpx
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from api import agentic_shopping, openai_transcription
from api.main import app


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", openai_transcription.TRANSCRIPTIONS_URL)
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("provider error", request=request, response=response)

    def json(self):
        return self.payload


def wav(samples, rate=16000):
    result = io.BytesIO()
    sf.write(result, samples, rate, format="WAV")
    return result.getvalue()


def test_transcription_uses_requested_model_and_preserves_raw_text(monkeypatch):
    seen = {}
    monkeypatch.setattr(openai_transcription, "OPENAI_API_KEY", "test-key")

    def fake_post(url, **kwargs):
        seen.update(url=url, **kwargs)
        return FakeResponse({"text": "  I need black sunny headphones.\n"})

    monkeypatch.setattr(openai_transcription.httpx, "post", fake_post)
    result = openai_transcription.transcribe_audio(b"RIFF-test")

    assert result == {"transcript": "  I need black sunny headphones.\n"}
    assert seen["data"] == {"model": "gpt-4o-transcribe", "response_format": "json"}
    assert seen["files"]["file"] == ("shopping.wav", b"RIFF-test", "audio/wav")
    assert seen["headers"]["Authorization"] == "Bearer test-key"


def test_transcription_fails_cleanly_without_key_or_usable_text(monkeypatch):
    monkeypatch.setattr(openai_transcription, "OPENAI_API_KEY", "")
    with pytest.raises(openai_transcription.TranscriptionUnavailable, match="OPENAI_API_KEY"):
        openai_transcription.transcribe_audio(b"audio")

    monkeypatch.setattr(openai_transcription, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_transcription.httpx, "post", lambda *a, **k: FakeResponse({"text": "  \n"}))
    with pytest.raises(openai_transcription.TranscriptionUnavailable, match="No speech"):
        openai_transcription.transcribe_audio(b"audio")


def test_transcription_hides_provider_failures(monkeypatch):
    monkeypatch.setattr(openai_transcription, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(openai_transcription.httpx, "post", lambda *a, **k: FakeResponse({}, 500))
    with pytest.raises(openai_transcription.TranscriptionUnavailable, match="cart was not changed") as error:
        openai_transcription.transcribe_audio(b"audio")
    assert "500" not in str(error.value)


def test_agentic_route_validates_audio_and_returns_transcript(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(
        agentic_shopping,
        "transcribe_audio",
        lambda raw: {"transcript": "Raw provider text"},
    )

    valid = wav(np.ones(16000, dtype=np.float32) * 0.1)
    response = client.post("/agentic-shopping/transcribe", files={"audio": ("request.wav", valid, "audio/wav")})
    assert response.status_code == 200
    assert response.json() == {"transcript": "Raw provider text"}

    assert client.post("/agentic-shopping/transcribe", files={"audio": ("empty.wav", b"")}).status_code == 400
    silent = wav(np.zeros(16000, dtype=np.float32))
    assert client.post("/agentic-shopping/transcribe", files={"audio": ("silent.wav", silent)}).status_code == 422
    wrong_rate = wav(np.ones(8000, dtype=np.float32) * 0.1, rate=8000)
    assert client.post("/agentic-shopping/transcribe", files={"audio": ("wrong.wav", wrong_rate)}).status_code == 400


def test_original_whisper_routes_remain_registered():
    paths = set(app.openapi()["paths"])
    assert "/shopping/voice" in paths
    assert "/shopping/text" in paths
    assert "/agentic-shopping/transcribe" in paths
