"""The ONLY place the ECAPA speaker model is loaded (CLAUDE.md §6).

Loaded once, at import, and warmed with one inference so the first real
verification does not pay the cold-start cost (docs/CONTEXT.md §12).
Reads the model from models/ecapa (scripts/warm_cache.py); never downloads.

This is speaker identity only. Nothing here transcribes (non-negotiable §2.1).
"""
import numpy as np
import torch
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

from ml.constants import ECAPA_DIR, ECAPA_EMBEDDING_DIM, ECAPA_SAMPLE_RATE

if not (ECAPA_DIR / "embedding_model.ckpt").exists():
    raise RuntimeError(f"ECAPA model missing at {ECAPA_DIR}. Run: python -m scripts.warm_cache")

_MODEL = EncoderClassifier.from_hparams(
    source=str(ECAPA_DIR),
    savedir=str(ECAPA_DIR),
    local_strategy=LocalStrategy.NO_LINK,  # no symlinks: they fail on Windows without Developer Mode
    run_opts={"device": "cpu"},
)
_MODEL.eval()


class AudioFormatError(ValueError):
    """The audio cannot be embedded as given. Raised, never silently fixed."""


def embed(waveform: np.ndarray, sample_rate: int) -> np.ndarray:
    """Mono float waveform at 16 kHz -> L2-normalized 192-dim float32 vector.

    The sample rate is asserted, not resampled: a mismatch between enrollment
    and verification produces low scores that look exactly like an identity
    mismatch (docs/ALGORITHM.md §7.1).
    """
    if sample_rate != ECAPA_SAMPLE_RATE:
        raise AudioFormatError(f"sample rate {sample_rate} Hz; the encoder requires {ECAPA_SAMPLE_RATE} Hz")
    if waveform.ndim != 1:
        raise AudioFormatError(f"expected mono audio, got shape {waveform.shape}")
    peak = float(np.max(np.abs(waveform))) if waveform.size else 0.0
    if peak == 0.0:
        raise AudioFormatError("audio is silent")

    normalized = torch.from_numpy((waveform / peak).astype(np.float32)).unsqueeze(0)
    with torch.no_grad():
        vector = _MODEL.encode_batch(normalized).reshape(-1).numpy()
    if vector.shape != (ECAPA_EMBEDDING_DIM,):
        raise RuntimeError(f"encoder returned shape {vector.shape}, expected ({ECAPA_EMBEDDING_DIM},)")
    return (vector / np.linalg.norm(vector)).astype(np.float32)


# Warm-up: one inference at import so the model is resident and fast.
embed(np.sin(np.linspace(0.0, 2 * np.pi * 220, ECAPA_SAMPLE_RATE)).astype(np.float32), ECAPA_SAMPLE_RATE)
