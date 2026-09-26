"""Waveform preprocessing candidates for the speaker embedding (docs/RESEARCH.md §2).

Pure numpy, no model. Energy only: nothing here recognizes words (§2.1).
"""
import numpy as np

from issuer.config import (CROP_HOP_S, CROP_S, SAMPLE_RATE, TRIM_DB_BELOW_PEAK, TRIM_FRAME_S, TRIM_HOP_S,
                           TRIM_KEEP_CONTEXT_S, TRIM_MIN_KEEP_S)


def frame_rms(waveform: np.ndarray, frame: int, hop: int) -> np.ndarray:
    count = 1 + (waveform.size - frame) // hop
    index = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    return np.sqrt(np.mean(np.square(waveform[index], dtype=np.float64), axis=1))


def trim_silence(waveform: np.ndarray) -> np.ndarray:
    """Drop stretches far quieter than the loudest frame, keeping context.

    Leading, trailing, and long internal pauses go; short gaps inside a sound
    survive because each voiced frame keeps TRIM_KEEP_CONTEXT_S around it. If
    too little would remain, the take is returned unchanged rather than
    embedding a fragment.
    """
    frame, hop = round(TRIM_FRAME_S * SAMPLE_RATE), round(TRIM_HOP_S * SAMPLE_RATE)
    if waveform.size < frame:
        return waveform
    rms = frame_rms(waveform, frame, hop)
    peak = float(rms.max())
    if peak <= 0:
        return waveform
    voiced = rms >= peak * 10 ** (-TRIM_DB_BELOW_PEAK / 20)
    context = round(TRIM_KEEP_CONTEXT_S / TRIM_HOP_S)
    kept = np.convolve(voiced.astype(np.float64), np.ones(2 * context + 1), mode="same") > 0.5
    starts = np.flatnonzero(kept) * hop
    edges = np.zeros(waveform.size + 1, dtype=np.int64)
    np.add.at(edges, starts, 1)
    np.add.at(edges, np.minimum(starts + frame, waveform.size), -1)
    trimmed = waveform[np.cumsum(edges[:-1]) > 0]
    return trimmed if trimmed.size >= TRIM_MIN_KEEP_S * SAMPLE_RATE else waveform


def crops(waveform: np.ndarray) -> list[np.ndarray]:
    """Overlapping CROP_S windows covering the whole take, last one flush with the end."""
    size, hop = round(CROP_S * SAMPLE_RATE), round(CROP_HOP_S * SAMPLE_RATE)
    if waveform.size <= size:
        return [waveform]
    starts = list(range(0, waveform.size - size + 1, hop))
    if starts[-1] != waveform.size - size:
        starts.append(waveform.size - size)
    return [waveform[s:s + size] for s in starts]
