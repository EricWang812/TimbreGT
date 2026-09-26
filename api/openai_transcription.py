"""OpenAI transcription for the additive agentic-shopping flow.

This module has one responsibility: audio bytes in, raw transcript out. It
does not interpret shopping intent, touch the catalog, mutate the cart, or call
the issuer. The existing local Whisper path in api/asr.py remains independent.
"""
import httpx

from api.config import OPENAI_API_KEY, OPENAI_TIMEOUT_S, OPENAI_TRANSCRIPTION_MODEL

TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"


class TranscriptionUnavailable(RuntimeError):
    """The transcription provider could not produce a usable transcript."""


def transcribe_audio(audio: bytes) -> dict[str, str]:
    """Return gpt-4o-transcribe's text exactly as received.

    The caller validates the recording container before it reaches this
    function. A fixed filename and content type avoid forwarding untrusted
    upload metadata to OpenAI.
    """
    if not OPENAI_API_KEY:
        raise TranscriptionUnavailable(
            "Agentic voice shopping is not configured yet. Add OPENAI_API_KEY on the merchant server."
        )

    try:
        response = httpx.post(
            TRANSCRIPTIONS_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            data={"model": OPENAI_TRANSCRIPTION_MODEL, "response_format": "json"},
            files={"file": ("shopping.wav", audio, "audio/wav")},
            timeout=OPENAI_TIMEOUT_S,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TranscriptionUnavailable(
            "OpenAI transcription is unavailable. Your cart was not changed; try again or use the existing shopping tools."
        ) from exc

    transcript = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(transcript, str) or not transcript.strip():
        raise TranscriptionUnavailable(
            "No speech was detected. Your cart was not changed; try again or use the existing shopping tools."
        )
    # Deliberately do not strip, normalize, or rewrite the provider's text.
    return {"transcript": transcript}
