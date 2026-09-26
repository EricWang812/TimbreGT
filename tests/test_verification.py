"""Enrollment math (docs/ALGORITHM.md §7.2, §7.3), recording checks, the
encoder contract, and the enrollment API.

Test audio is synthetic tones: it exercises the plumbing only. It is never
speech and never an imitation of disordered speech (non-negotiable §2.3).
"""
import io
import math

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from issuer import db as issuer_db
from issuer import enrollment
from issuer import verification as v
from issuer.config import (
    COHESION_MIN,
    CONFIDENT_MARGIN,
    EMBEDDING_DIM,
    GLOBAL_FLOOR,
    LABELS_PER_USER,
    MAX_DRIFT,
    MIN_DURATION,
    RECORDINGS_PER_LABEL,
    SAMPLE_RATE,
    THRESHOLD_MARGIN,
)
from issuer.main import app as issuer_app
from ml.encoder import AudioFormatError, embed

USER_ID = "enroll-test-user"


def tone(seconds=1.6, freq=220.0, amp=0.3, rate=SAMPLE_RATE, seed=0):
    t = np.arange(int(seconds * rate)) / rate
    noise = np.random.default_rng(seed).normal(0, 0.01, t.size)
    return (amp * np.sin(2 * np.pi * freq * t) + noise).astype(np.float32)


def wav_bytes(waveform, rate=SAMPLE_RATE):
    buf = io.BytesIO()
    sf.write(buf, waveform, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# --- §7.2 / §7.3 math -------------------------------------------------------

def test_cohesion_excludes_the_diagonal():
    identical = np.tile(np.eye(4, dtype=np.float32)[0], (5, 1))
    assert v.cohesion(identical) == pytest.approx(1.0)
    orthogonal = np.eye(3, dtype=np.float32)
    assert v.cohesion(orthogonal) == pytest.approx(0.0)


def test_cohesion_known_value():
    e1, e2 = np.eye(2, dtype=np.float32)
    mid = (e1 + e2) / math.sqrt(2)
    # Pairs: e1.e2 = 0, e1.mid = e2.mid = 1/sqrt(2); mean over the 3 pairs.
    assert v.cohesion(np.stack([e1, e2, mid])) == pytest.approx((2 / math.sqrt(2)) / 3, abs=1e-6)


def test_centroid_is_unit_length():
    rng = np.random.default_rng(1)
    vecs = rng.normal(size=(5, 192)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    assert np.linalg.norm(v.centroid(vecs)) == pytest.approx(1.0, abs=1e-6)


def test_spread_is_held_out_known_value():
    # ADR 3. Three orthonormal samples: each one's leave-one-out centroid is
    # (other1 + other2)/sqrt(2), orthogonal to it, so held-out spread is 0.
    # The in-sample version would claim 1/sqrt(3).
    vecs = np.eye(3, dtype=np.float32)
    assert v.spread(vecs) == pytest.approx(0.0, abs=1e-6)
    assert v.in_sample_spread(vecs) == pytest.approx(1 / math.sqrt(3), abs=1e-6)


def test_held_out_spread_is_below_in_sample_and_the_gap_grows_with_variability():
    rng = np.random.default_rng(2)
    base = rng.normal(size=192)

    def takes(noise):
        vecs = base + rng.normal(scale=noise, size=(5, 192))
        return (vecs / np.linalg.norm(vecs, axis=1, keepdims=True)).astype(np.float32)

    steady, variable = takes(0.3), takes(1.5)
    gap_steady = v.in_sample_spread(steady) - v.spread(steady)
    gap_variable = v.in_sample_spread(variable) - v.spread(variable)
    assert 0 < gap_steady < gap_variable


def test_personal_threshold_uses_margin_but_never_goes_below_floor():
    assert v.personal_threshold(0.9) == pytest.approx(0.9 - THRESHOLD_MARGIN)
    assert v.personal_threshold(GLOBAL_FLOOR) == GLOBAL_FLOOR   # margin would go below the floor


# --- Recording checks -------------------------------------------------------

@pytest.mark.parametrize(("waveform", "phrase"), [
    (tone(seconds=MIN_DURATION - 0.3), "Hold the sound a little longer"),
    (tone(amp=0.001), "too quiet"),
    (tone(seconds=11), "Keep it under"),
])
def test_bad_recordings_get_an_actionable_message(waveform, phrase):
    with pytest.raises(v.RecordingRejected, match=phrase):
        v.check_recording(waveform)


def test_good_recording_passes():
    v.check_recording(tone())


@pytest.mark.parametrize("data", [
    wav_bytes(tone(), rate=44100),
    wav_bytes(np.stack([tone(), tone()], axis=1)),
    b"not audio",
], ids=["wrong-rate", "stereo", "not-audio"])  # explicit ids: raw bytes as ids overflow a Windows env var
def test_decode_upload_rejects_wrong_format_instead_of_fixing_it(data):
    with pytest.raises(v.RecordingRejected):
        v.decode_upload(data)


# --- Encoder contract (§7.1) --------------------------------------------------

def test_encoder_returns_deterministic_unit_vectors():
    a, b = embed(tone(), SAMPLE_RATE), embed(tone(), SAMPLE_RATE)
    assert a.shape == (192,) and a.dtype == np.float32
    assert np.linalg.norm(a) == pytest.approx(1.0, abs=1e-5)
    assert np.allclose(a, b)


def test_encoder_refuses_to_resample():
    with pytest.raises(AudioFormatError, match="16000"):
        embed(tone(rate=8000), 8000)


# --- Enrollment API ------------------------------------------------------------

@pytest.fixture
def issuer():
    with TestClient(issuer_app) as client:
        with issuer_db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO users VALUES (?, 'Enroll Test', '2026-01-01T00:00:00+00:00')",
                         (USER_ID,))
            for table in ("enroll_samples", "templates", "enroll_labels"):
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (USER_ID,))
        yield client


def _record(client, label, i=0, **tone_args):
    return client.post(f"/v1/enroll/{USER_ID}/samples", data={"label": label},
                       files={"audio": ("rec.wav", wav_bytes(tone(seed=i, **tone_args)), "audio/wav")})


def _record_all(client, label):
    for i in range(RECORDINGS_PER_LABEL):
        res = _record(client, label, i)
        assert res.status_code == 200, res.text
        assert res.json() == {"label": label, "samples": i + 1, "needed": RECORDINGS_PER_LABEL}


def test_enroll_a_label_end_to_end(issuer):
    _record_all(issuer, "hum")
    assert _record(issuer, "hum", 9).status_code == 409                 # no sixth recording
    res = issuer.post(f"/v1/enroll/{USER_ID}/labels/hum/finalize").json()
    assert res["status"] == "enrolled"
    assert res["threshold"] == pytest.approx(max(GLOBAL_FLOOR, res["spread"] - THRESHOLD_MARGIN), abs=1e-3)
    row = issuer_db.fetch_one("SELECT centroid, low_confidence FROM templates WHERE user_id = ? AND label = 'hum'",
                              (USER_ID,))
    assert np.frombuffer(row["centroid"], dtype=np.float32).shape == (192,)
    assert row["low_confidence"] == 0
    progress = issuer.get(f"/v1/enroll/{USER_ID}").json()
    assert progress["labels"] == [{"label": "hum", "status": "enrolled", "samples": 5, "rerecords_left": 1}]


def test_short_recording_is_rejected_with_its_message(issuer):
    res = _record(issuer, "ah", seconds=0.5)
    assert res.status_code == 422
    assert "Hold the sound a little longer" in res.json()["detail"]


def test_finalize_requires_all_recordings(issuer):
    _record(issuer, "ah")
    assert issuer.post(f"/v1/enroll/{USER_ID}/labels/ah/finalize").status_code == 409


def test_at_most_three_labels(issuer):
    for i, label in enumerate(["one", "two", "three"][:LABELS_PER_USER]):
        assert _record(issuer, label, i).status_code == 200
    assert _record(issuer, "four").status_code == 409


def test_low_cohesion_rerecords_once_then_accepts_as_low_confidence(issuer, monkeypatch):
    # §7.2 and non-negotiable §2.4: never hard-fail enrollment.
    monkeypatch.setattr(enrollment.v, "cohesion", lambda embeddings: COHESION_MIN - 0.2)
    _record_all(issuer, "hum")
    first = issuer.post(f"/v1/enroll/{USER_ID}/labels/hum/finalize").json()
    assert first["status"] == "rerecord"
    assert issuer.get(f"/v1/enroll/{USER_ID}").json()["labels"][0]["samples"] == 0   # samples cleared

    _record_all(issuer, "hum")
    second = issuer.post(f"/v1/enroll/{USER_ID}/labels/hum/finalize").json()
    assert second["status"] == "low_confidence"
    assert "passkey" in second["message"]
    labels = issuer.get(f"/v1/enroll/{USER_ID}").json()["labels"]
    assert labels == [{"label": "hum", "status": "low_confidence", "samples": 5, "rerecords_left": 0}]


def test_finalize_after_start_over_cannot_leave_a_hidden_template(issuer):
    _record_all(issuer, "hum")
    issuer.delete(f"/v1/enroll/{USER_ID}/labels/hum")
    assert issuer.post(f"/v1/enroll/{USER_ID}/labels/hum/finalize").status_code == 404
    assert issuer_db.fetch_one("SELECT 1 FROM templates WHERE user_id = ?", (USER_ID,)) is None


def test_start_over_removes_a_label_entirely(issuer):
    _record_all(issuer, "hum")
    issuer.post(f"/v1/enroll/{USER_ID}/labels/hum/finalize")
    progress = issuer.delete(f"/v1/enroll/{USER_ID}/labels/hum").json()
    assert progress["labels"] == []
    assert issuer_db.fetch_one("SELECT 1 FROM templates WHERE user_id = ?", (USER_ID,)) is None


def _unit_vec(seed):
    x = np.random.default_rng(seed).normal(size=EMBEDDING_DIM).astype(np.float32)
    return x / np.linalg.norm(x)


def _near(center, similarity, seed):
    """A unit vector with the given cosine to center."""
    other = _unit_vec(seed)
    other = other - (other @ center) * center
    other /= np.linalg.norm(other)
    return (similarity * center + math.sqrt(1 - similarity ** 2) * other).astype(np.float32)


def test_adapt_skips_a_borderline_pass():
    center, threshold = _unit_vec(1), 0.6
    take = _near(center, threshold + 0.05, seed=2)       # passes, but not confidently
    new, drift = v.adapt(center, take, threshold)
    assert drift is None and np.array_equal(new, center)


def test_adapt_moves_toward_a_confident_take_and_stays_unit():
    center, threshold = _unit_vec(3), 0.6
    take = _near(center, 0.8, seed=4)
    new, drift = v.adapt(center, take, threshold)
    assert 0 < drift <= MAX_DRIFT
    assert np.isclose(np.linalg.norm(new), 1, atol=1e-5)
    assert new @ take > center @ take


def test_adapt_clamp_holds_even_with_a_large_step():
    center, threshold = _unit_vec(5), 0.0
    take = _near(center, 0.2, seed=6)                    # far away, gate forced open
    new, drift = v.adapt(center, take, threshold - 1, alpha=0.9)
    assert np.isclose(drift, MAX_DRIFT, atol=1e-4)
    assert new @ center >= 1 - MAX_DRIFT - 1e-6


def test_repeated_adaptation_moves_at_most_max_drift_per_update():
    center, threshold = _unit_vec(7), 0.45
    for i in range(50):
        take = _near(center, threshold + CONFIDENT_MARGIN + 0.001, seed=100 + i)  # just past the gate
        new, drift = v.adapt(center, take, threshold)
        assert drift is not None and new @ center >= 1 - MAX_DRIFT - 1e-6
        center = new
