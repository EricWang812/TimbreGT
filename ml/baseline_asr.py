"""The losing baseline: a transcription-based check, for demo contrast only.

Models what voice-gated systems do today (IVR prompts, "say your passphrase"):
transcribe the take and accept it only if the words match the prompt. It
measures intelligibility, not identity. Never imported by issuer/ (non-negotiable
§2.1, enforced by tests/test_guards.py). No model is loaded at import.
"""
from functools import lru_cache
import re

import numpy as np

from issuer.config import BASELINE_MAX_WER
from ml.constants import WHISPER_DIR

DIGITS = dict(zip("0123456789", "zero one two three four five six seven eight nine".split()))


def normalize(text):
    """Lowercase words, punctuation dropped, single digits spelled out."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    return [DIGITS.get(w, w) for w in (w.strip("'") for w in words) if w]


def scoreable(prompt):
    """A prompt with plain words to compare against.

    TORGO also has instructions such as "[say Ah-P-Eee repeatedly]", "xxx"
    placeholders, and a few garbled transcriptions ("lieDDDDDDDDDCCCC"); a
    transcription check has no fair expected text for those.
    """
    return ("[" not in prompt and "xxx" not in prompt.lower() and not re.search(r"(.)\1{3,}", prompt)
            and bool(normalize(prompt)))


def wer(reference, hypothesis):
    """Word error rate: word-level edit distance over reference length."""
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        raise ValueError("Reference prompt has no words")
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        previous, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (r != h))
    return row[-1] / len(ref)


def passes(reference, hypothesis):
    return wer(reference, hypothesis) <= BASELINE_MAX_WER


@lru_cache(maxsize=1)
def _model():
    if not (WHISPER_DIR / "model.bin").exists():
        raise RuntimeError(f"Whisper small missing at {WHISPER_DIR}. Run: python -m scripts.warm_asr")
    from faster_whisper import WhisperModel
    return WhisperModel(str(WHISPER_DIR), device="cpu", compute_type="int8", local_files_only=True)


def transcribe(waveform):
    """16 kHz mono float32 -> best transcript (English, beam search)."""
    segments, _ = _model().transcribe(np.asarray(waveform, dtype=np.float32), language="en", beam_size=5,
                                      condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segments).strip()


def compare(trials):
    """Acceptance rates for both checks over identical trials, per claimed group.

    Each trial is one take scored against one claimed identity: kind is
    "genuine" (the take's own speaker) or "impostor" (another speaker's
    template). baseline_pass ignores the claim entirely, which is the point:
    anyone who says the prompt clearly passes it.
    """
    out = {}
    for group in ("control", "dysarthric"):
        genuine = [t for t in trials if t["kind"] == "genuine" and t["claimed_group"] == group]
        impostor = [t for t in trials if t["kind"] == "impostor" and t["claimed_group"] == group]
        if not genuine or not impostor:
            raise ValueError(f"Both genuine and impostor {group} trials are required")
        out[group] = {
            "speakers": len({t["claimed"] for t in genuine}),
            "genuine_trials": len(genuine), "impostor_trials": len(impostor),
            "baseline_accepts_genuine": float(np.mean([t["baseline_pass"] for t in genuine])),
            "timbre_accepts_genuine": float(np.mean([t["timbre_pass"] for t in genuine])),
            "baseline_accepts_impostor": float(np.mean([t["baseline_pass"] for t in impostor])),
            "timbre_accepts_impostor": float(np.mean([t["timbre_pass"] for t in impostor])),
        }
    return out
