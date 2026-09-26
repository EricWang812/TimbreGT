"""Liveness and anti-replay (docs/ALGORITHM.md §7.5). Pure functions.

1. Randomized challenge: CHALLENGE_LENGTH of the person's usable sounds, in a
   random order, so one stolen recording cannot satisfy the sequence.
2. Near-duplicate rejection: a take that correlates above REPLAY_CORR with any
   stored sample is the same audio replayed, and fails.
(3. Amount tiering lives with the session logic in issuer/approvals.py.)
"""
import secrets

import numpy as np
from scipy.signal import correlate

from issuer.config import CHALLENGE_LENGTH, REPLAY_CORR

_rng = secrets.SystemRandom()  # challenge order must not be predictable


def pick_challenge(usable_labels: list[str]) -> list[str]:
    if len(usable_labels) < CHALLENGE_LENGTH:
        raise ValueError(f"need at least {CHALLENGE_LENGTH} usable sounds, have {len(usable_labels)}")
    return _rng.sample(usable_labels, CHALLENGE_LENGTH)


def max_normalized_xcorr(a: np.ndarray, b: np.ndarray) -> float:
    """Peak of the normalized cross-correlation over all lags, in [0, 1].
    1.0 means one waveform is an exact (shifted, scaled) copy of the other."""
    a = a.astype(np.float64) - a.mean()
    b = b.astype(np.float64) - b.mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0.0:
        return 0.0
    return float(np.max(np.abs(correlate(a, b, mode="full", method="fft"))) / denom)


def is_replay(take: np.ndarray, stored: list[np.ndarray]) -> bool:
    """True if the take is a near-duplicate of any stored sample.

    This catches the same file replayed. It does not catch a recording played
    through a speaker into a microphone; the randomized challenge and the
    amount-tiered passkey step-up cover that (docs/CONTEXT.md §16)."""
    return any(max_normalized_xcorr(take, s) >= REPLAY_CORR for s in stored)
