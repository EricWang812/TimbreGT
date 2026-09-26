"""Additive OpenAI agentic-shopping routes.

These routes are separate from /shopping/voice and /shopping/text so the
working local Whisper shopping path remains available without behavioral
changes. The router keeps transcription and intent extraction as separate
operations, then exposes clarification and finalization boundaries. Later
stages attach commerce-agent endpoints.
"""
import io
import sqlite3

import numpy as np
import soundfile as sf
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from api.ambiguity_resolution import (
    ClarificationAnswer,
    ClarificationState,
    ResolutionError,
    apply_clarification_answer,
    build_clarification_state,
)
from api.config import SHOP_AUDIO_MAX_BYTES, SHOP_AUDIO_MAX_SECONDS, SHOP_SAMPLE_RATE, SHOP_TEXT_MAX
from api.commerce_agent import CommerceError, CommerceRequest, CommerceResult, prepare_commerce_cart
from api.final_intent import FinalIntentError, FinalizedShoppingRequest, finalize_shopping_intent
from api.openai_intent import IntentUnavailable, ShoppingIntent, extract_shopping_intent
from api.openai_transcription import TranscriptionUnavailable, transcribe_audio

router = APIRouter(prefix="/agentic-shopping", tags=["agentic shopping"])


class TranscriptionResponse(BaseModel):
    transcript: str


class IntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: str = Field(max_length=SHOP_TEXT_MAX)

    @field_validator("transcript")
    @classmethod
    def transcript_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("transcript must contain speech")
        # Validate only. Returning the original string preserves provider text.
        return value


class IntentResponse(BaseModel):
    rawTranscript: str
    extractedIntent: ShoppingIntent


class ClarificationAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ClarificationState
    answer: ClarificationAnswer


def _read_valid_recording(audio: UploadFile) -> bytes:
    raw = audio.file.read(SHOP_AUDIO_MAX_BYTES + 1)
    if not raw:
        raise HTTPException(400, "The recording was empty. Try again or use the existing shopping tools.")
    if len(raw) > SHOP_AUDIO_MAX_BYTES:
        raise HTTPException(413, "That recording is too long. Try a shorter request.")
    try:
        waveform, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
    except (sf.LibsndfileError, RuntimeError) as exc:
        raise HTTPException(400, "Could not read that recording. Try again or use the existing shopping tools.") from exc
    if (rate != SHOP_SAMPLE_RATE or waveform.ndim != 1 or waveform.size == 0
            or waveform.size > SHOP_AUDIO_MAX_SECONDS * SHOP_SAMPLE_RATE
            or not np.isfinite(waveform).all()):
        raise HTTPException(400, "Use a short mono 16 kHz recording.")
    if not np.any(waveform):
        raise HTTPException(422, "No speech was detected. Try again or use the existing shopping tools.")
    return raw


@router.post("/transcribe", response_model=TranscriptionResponse)
def transcribe_agentic_request(audio: UploadFile = File(...)) -> TranscriptionResponse:
    raw = _read_valid_recording(audio)
    try:
        return TranscriptionResponse(**transcribe_audio(raw))
    except TranscriptionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/intent", response_model=IntentResponse)
def interpret_agentic_request(body: IntentRequest) -> IntentResponse:
    try:
        intent = extract_shopping_intent(body.transcript)
    except IntentUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    return IntentResponse(rawTranscript=body.transcript, extractedIntent=intent)


@router.post("/clarifications", response_model=ClarificationState)
def start_agentic_clarifications(body: IntentResponse) -> ClarificationState:
    try:
        return build_clarification_state(body.rawTranscript, body.extractedIntent)
    except ResolutionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/clarifications/answer", response_model=ClarificationState)
def answer_agentic_clarification(body: ClarificationAnswerRequest) -> ClarificationState:
    try:
        return apply_clarification_answer(body.state, body.answer)
    except ResolutionError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/finalize", response_model=FinalizedShoppingRequest)
def finalize_agentic_request(state: ClarificationState) -> FinalizedShoppingRequest:
    try:
        return finalize_shopping_intent(state)
    except FinalIntentError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/commerce/prepare-cart", response_model=CommerceResult)
def prepare_agentic_cart(body: CommerceRequest) -> CommerceResult:
    try:
        return prepare_commerce_cart(body)
    except CommerceError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (sqlite3.Error, ValidationError) as exc:
        raise HTTPException(503, "Product search is unavailable. Your cart was not changed.") from exc
