"""Merchant-owned shopping audio. No connection to enrollment or approval."""
import io
import logging

import numpy as np
import soundfile as sf
from fastapi import Depends, APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from api import asr
from api.catalog import list_catalog
from api.catalog import shopping_market
from api.config import SHOP_AUDIO_MAX_BYTES, SHOP_AUDIO_MAX_SECONDS, SHOP_SAMPLE_RATE, SHOP_TEXT_MAX
from api.llm import rerank

router = APIRouter(dependencies=[Depends(shopping_market)])
log = logging.getLogger(__name__)


class TextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=SHOP_TEXT_MAX)


def result_for(hypotheses):
    result = rerank(hypotheses, list_catalog())
    return {**result, "hypotheses": hypotheses}


@router.post("/shopping/text")
def text_intent(body: TextRequest):
    return result_for([body.text.strip()])


@router.post("/shopping/voice")
def voice_intent(audio: UploadFile = File(...)):
    raw = audio.file.read(SHOP_AUDIO_MAX_BYTES + 1)
    if len(raw) > SHOP_AUDIO_MAX_BYTES:
        raise HTTPException(413, "That recording is too long. Try one item, or use the product buttons.")
    try:
        waveform, rate = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
    except (sf.LibsndfileError, RuntimeError) as exc:
        raise HTTPException(400, "Could not read that recording. Type an item or use the product buttons.") from exc
    if (rate != SHOP_SAMPLE_RATE or waveform.ndim != 1 or waveform.size == 0
            or waveform.size > SHOP_AUDIO_MAX_SECONDS * SHOP_SAMPLE_RATE or not np.isfinite(waveform).all()):
        raise HTTPException(400, "Use a short mono 16 kHz recording, or type an item.")
    if not np.any(waveform):
        return result_for([])
    try:
        return result_for(asr.hypotheses(waveform))
    except asr.ASRUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (RuntimeError, ValueError, OSError) as exc:
        log.warning("Shopping ASR failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Voice shopping is unavailable. Type an item or use the product buttons.") from exc
