"""Enrollment and verification math (docs/ALGORITHM.md §7).

Every number comes from issuer/config.py. Embeddings are L2-normalized, so
cosine similarity is a plain dot product (§7.1).
"""
import io

import numpy as np
import soundfile as sf

from issuer.config import (
    ALPHA,
    CONFIDENT_MARGIN,
    GLOBAL_FLOOR,
    MAX_DRIFT,
    MAX_DURATION,
    MIN_DURATION,
    MIN_RMS,
    SAMPLE_RATE,
    THRESHOLD_MARGIN,
)


class RecordingRejected(ValueError):
    """A recording the UI should ask the person to redo. `str(exc)` is the
    message shown to them: specific and actionable, never a dead end (§2.4)."""


def decode_upload(data: bytes) -> np.ndarray:
    """WAV bytes from the browser -> mono float32 waveform at SAMPLE_RATE.

    The browser resamples to 16 kHz before upload (CLAUDE.md §6). Anything
    else is rejected here rather than resampled (§7.1).
    """
    try:
        waveform, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    except (sf.LibsndfileError, RuntimeError) as exc:
        raise RecordingRejected("That recording could not be read. Please record it again.") from exc
    if rate != SAMPLE_RATE:
        raise RecordingRejected(f"Audio arrived at {rate} Hz; expected {SAMPLE_RATE} Hz. Please reload the page.")
    if waveform.ndim != 1:
        raise RecordingRejected("Audio arrived in stereo; expected mono. Please reload the page.")
    return waveform


def check_recording(waveform: np.ndarray) -> None:
    """§7.2 step 1: reject what cannot make a stable voiceprint, with a message
    that says what to do differently."""
    duration = waveform.size / SAMPLE_RATE
    if duration < MIN_DURATION:
        raise RecordingRejected(
            f"That was {duration:.1f} seconds. Hold the sound a little longer, at least {MIN_DURATION:g} seconds."
        )
    if duration > MAX_DURATION:
        raise RecordingRejected(f"That was {duration:.0f} seconds. Keep it under {MAX_DURATION:g} seconds.")
    rms = float(np.sqrt(np.mean(np.square(waveform, dtype=np.float64))))
    if rms < MIN_RMS:
        raise RecordingRejected("That was too quiet to use. Move a little closer to the microphone and try again.")


def cohesion(embeddings: np.ndarray) -> float:
    """Mean pairwise cosine across samples, excluding each sample with itself."""
    n = embeddings.shape[0]
    if n < 2:
        raise ValueError("cohesion needs at least two embeddings")
    sims = embeddings @ embeddings.T
    return float((sims.sum() - np.trace(sims)) / (n * (n - 1)))


def centroid(embeddings: np.ndarray) -> np.ndarray:
    mean = embeddings.mean(axis=0)
    return (mean / np.linalg.norm(mean)).astype(np.float32)


def spread(embeddings: np.ndarray) -> float:
    """§7.2 step 4, held out (docs/DECISIONS.md ADR 3): the mean cosine of each
    sample to the centroid of the OTHER samples. This estimates how a fresh
    take will score at checkout. The in-sample version includes each sample in
    its own centroid, overstating consistency most for the people whose takes
    vary most, which is backwards for a personal threshold."""
    n = embeddings.shape[0]
    if n < 2:
        raise ValueError("spread needs at least two embeddings")
    return float(np.mean([embeddings[i] @ centroid(np.delete(embeddings, i, axis=0)) for i in range(n)]))


def in_sample_spread(embeddings: np.ndarray) -> float:
    """The original §7.2 definition, kept only so the Phase 8 evaluation can
    report both variants side by side. Not used for live thresholds."""
    return float(np.mean(embeddings @ centroid(embeddings)))


def score(embedding: np.ndarray, center: np.ndarray) -> float:
    """Cosine similarity of a take to a template (both unit length, §7.1)."""
    return float(embedding @ center)


def personal_threshold(template_spread: float) -> float:
    """§7.3: looser for a speaker whose own recordings vary more, but never
    below the global security floor."""
    return max(GLOBAL_FLOOR, template_spread - THRESHOLD_MARGIN)


def _unit(vector: np.ndarray) -> np.ndarray:
    return (vector / np.linalg.norm(vector)).astype(np.float32)


def adapt(center: np.ndarray, embedding: np.ndarray, threshold: float,
          alpha: float = ALPHA, max_drift: float = MAX_DRIFT) -> tuple[np.ndarray, float | None]:
    """§7.4: move the template a little toward a confident take.

    Returns (new template, drift), where drift is 1 - cos(new, old). A take
    below threshold + CONFIDENT_MARGIN returns the template unchanged and
    drift None: a borderline pass must never move it. The clamp keeps any one
    update within max_drift, so repeated passes cannot walk the template far
    toward another voice. alpha and max_drift are parameters only so tests can
    force the clamp; callers use the config values.
    """
    if score(embedding, center) < threshold + CONFIDENT_MARGIN:
        return center, None
    floor = 1 - max_drift
    mix = lambda t: _unit((1 - t) * center + t * embedding)  # noqa: E731
    new = mix(alpha)
    if float(new @ center) < floor:
        # cos(mix(t), center) falls monotonically as t grows toward the take,
        # so bisect for the largest step that still honours the clamp.
        low, high = 0.0, alpha
        for _ in range(40):
            mid = (low + high) / 2
            low, high = (mid, high) if float(mix(mid) @ center) >= floor else (low, mid)
        new = mix(low)
    return new, float(1 - new @ center)
