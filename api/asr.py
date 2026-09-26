"""Shopping-only n-best decoding. Never imported by the issuer."""
from functools import lru_cache
import re
from threading import Lock

import numpy as np

from api.config import ASR_BEAM_SIZE, ASR_MAX_TOKENS, ASR_NBEST, ASR_NO_SPEECH_MAX, ASR_MODEL_DIR

_LOCK = Lock()


class ASRUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _model():
    if not (ASR_MODEL_DIR / "model.bin").exists():
        raise ASRUnavailable("Voice shopping is not set up yet. Use the product buttons or type an item.")
    from faster_whisper import WhisperModel
    return WhisperModel(str(ASR_MODEL_DIR), device="cpu", compute_type="int8", local_files_only=True)


def hypotheses(waveform):
    # WhisperModel.transcribe exposes only its best sequence. Use its existing
    # CTranslate2 decoder to return true beam hypotheses from one short window.
    from faster_whisper.audio import pad_or_trim
    from faster_whisper.tokenizer import Tokenizer
    with _LOCK:
        model = _model()
        tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task="transcribe", language="en")
        # The encoder accepts exactly one 30 s window (3000 frames); a short
        # clip must be zero-padded, as WhisperModel.transcribe does internally.
        features = pad_or_trim(model.feature_extractor(waveform), model.feature_extractor.nb_max_frames)
        encoded = model.encode(features)
        result = model.model.generate(
            encoded, [tokenizer.sot_sequence + [tokenizer.no_timestamps]],
            beam_size=ASR_BEAM_SIZE, num_hypotheses=ASR_BEAM_SIZE,
            max_length=ASR_MAX_TOKENS, return_scores=True, return_no_speech_prob=True,
            sampling_topk=1,
        )[0]
        if result.no_speech_prob > ASR_NO_SPEECH_MAX:
            return []
        # Beams often differ only in case or punctuation ("Delta." vs "delta");
        # keep distinct wordings so the reranker sees real alternatives.
        texts, seen = [], set()
        for tokens in result.sequences_ids:
            text = tokenizer.decode(tokens).strip()
            key = " ".join(re.findall(r"[a-z0-9']+", text.lower()))
            if key and key not in seen:
                seen.add(key)
                texts.append(text)
        return texts[:ASR_NBEST]
