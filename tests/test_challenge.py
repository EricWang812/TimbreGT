"""Voice challenge at checkout (docs/ALGORITHM.md §7.5, §7.6).

The test user is enrolled with three synthetic tones (one "sound" per
frequency). Tones exercise the plumbing only; they are never speech and never
an imitation of disordered speech (non-negotiable §2.3). Whether a mismatch is
rejected is tested by forcing the score, not by relying on how the speaker
model happens to rank two tones.
"""
import io
import json
import uuid

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from issuer import approvals
from issuer import db as issuer_db
from issuer.config import CHALLENGE_LENGTH, MAX_DRIFT, MAX_VOICE_ATTEMPTS, SAMPLE_RATE, STEP_UP_AMOUNT
from issuer.liveness import is_replay, max_normalized_xcorr, pick_challenge
from issuer.main import app as issuer_app
from tests.softauthn import pay_with_passkey, register

USER_ID = "voice-test-user"
SOUNDS = {"low": 220.0, "mid": 440.0, "high": 880.0}
DEVICE = {}  # the test user's registered soft passkey


def tone(freq, seed, seconds=1.6):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    noise = np.random.default_rng(seed).normal(0, 0.01, t.size)
    return (0.3 * np.sin(2 * np.pi * freq * t) + noise).astype(np.float32)


def take(label, seed, seconds=1.6):
    """One take of a sound: a small seeded pitch variation (+/-4%), as real
    takes vary. Without it, two takes of a pure tone correlate at about 0.998
    and the replay check (correctly) calls the second one a replay."""
    jitter = np.random.default_rng(seed + 1000).uniform(-0.04, 0.04)
    return tone(SOUNDS[label] * (1 + jitter), seed, seconds)


def wav(waveform):
    buf = io.BytesIO()
    sf.write(buf, waveform, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# --- Liveness functions -------------------------------------------------------

def test_challenge_is_distinct_sounds_of_the_right_length():
    for _ in range(20):
        picked = pick_challenge(list(SOUNDS))
        assert len(picked) == CHALLENGE_LENGTH and len(set(picked)) == CHALLENGE_LENGTH
        assert set(picked) <= set(SOUNDS)
    with pytest.raises(ValueError):
        pick_challenge(["only-one"])


def test_challenge_order_varies():
    assert len({tuple(pick_challenge(list(SOUNDS))) for _ in range(60)}) > 1


def test_replay_detection():
    original = tone(220, seed=1)
    assert max_normalized_xcorr(original, original) == pytest.approx(1.0, abs=1e-6)
    shifted = np.concatenate([np.zeros(800, dtype=np.float32), original])   # same audio, 50 ms later
    assert is_replay(shifted, [original])
    unrelated = np.random.default_rng(9).normal(0, 0.3, original.size).astype(np.float32)
    assert not is_replay(unrelated, [original])


# --- Flow ------------------------------------------------------------------------

@pytest.fixture(scope="module")
def enrolled():
    """Enroll the test user once: three tone "sounds", five takes each."""
    with TestClient(issuer_app) as client:
        with issuer_db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO users VALUES (?, 'Voice Test', '2026-01-01T00:00:00+00:00')",
                         (USER_ID,))
            conn.execute(
                "INSERT INTO payment_tokens (user_id, token_value, last_four, nickname, created_at)"
                " SELECT ?, 'fake_tok_voice', '4242', 'Visa', '2026-01-01T00:00:00+00:00'"
                " WHERE NOT EXISTS (SELECT 1 FROM payment_tokens WHERE user_id = ?)", (USER_ID, USER_ID))
            for table in ("enroll_samples", "templates", "enroll_labels"):
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (USER_ID,))
        for label in SOUNDS:
            for i in range(5):
                res = client.post(f"/v1/enroll/{USER_ID}/samples", data={"label": label},
                                  files={"audio": ("t.wav", wav(take(label, seed=i)), "audio/wav")})
                assert res.status_code == 200, res.text
            assert client.post(f"/v1/enroll/{USER_ID}/labels/{label}/finalize").json()["status"] == "enrolled"
        DEVICE["passkey"] = register(client, USER_ID)
    return USER_ID


@pytest.fixture
def issuer(enrolled):
    with TestClient(issuer_app) as client:
        yield client


def _session(client, amount_cents=1234):
    res = client.post("/v1/sessions", json={
        "instruction_id": str(uuid.uuid4()), "amount_cents": amount_cents, "merchant_id": "test-merchant"})
    return res.json()["session_id"]


def _identify(client, sid, user_id=USER_ID):
    res = client.post(f"/v1/sessions/{sid}/identify", json={"user_id": user_id})
    assert res.status_code == 200, res.text
    return res.json()


def _answer(client, sid, labels, seed=100, **overrides):
    files = [("audio", (f"{i}.wav", overrides.get(label) or wav(take(label, seed=seed + i)), "audio/wav"))
             for i, label in enumerate(labels)]
    return client.post(f"/v1/sessions/{sid}/voice", files=files)


def _approve(client, sid):
    instruction_id = issuer_db.fetch_one("SELECT instruction_id FROM sessions WHERE id = ?", (sid,))[0]
    return client.post("/v1/approve", json={"instruction_id": instruction_id}).json()


def test_identify_issues_a_stable_challenge(issuer):
    sid = _session(issuer)
    first = _identify(issuer, sid)
    assert first["mode"] == "voice" and first["attempts_left"] == MAX_VOICE_ATTEMPTS
    assert len(first["challenge"]) == CHALLENGE_LENGTH
    # Re-identifying must not re-roll the challenge.
    assert _identify(issuer, sid)["challenge"] == first["challenge"]


def test_matching_voice_approves_and_merchant_learns_two_keys(issuer):
    sid = _session(issuer)
    challenge = _identify(issuer, sid)["challenge"]
    res = _answer(issuer, sid, challenge).json()
    assert res["result"] == "verified", res
    assert [t["label"] for t in res["takes"]] == challenge
    assert all(t["passed"] and not t["replay"] and t["score"] >= t["threshold"] for t in res["takes"])
    assert res["latency_ms"] >= 0
    assert set(_approve(issuer, sid)) == {"verified", "transaction_id"}
    assert _approve(issuer, sid)["verified"] is True
    row = issuer_db.fetch_one("SELECT method FROM sessions WHERE id = ?", (sid,))
    assert row["method"] == "voice"
    logged = issuer_db.fetch_all("SELECT passed FROM verifications WHERE session_id = ?", (sid,))
    assert [r["passed"] for r in logged] == [1] * CHALLENGE_LENGTH


def test_two_failures_fall_back_to_passkey(issuer, monkeypatch):
    monkeypatch.setattr(approvals.v, "score", lambda embedding, center: 0.0)
    sid = _session(issuer)
    challenge = _identify(issuer, sid)["challenge"]
    assert issuer.post(f"/v1/sessions/{sid}/passkey/options").status_code == 409   # voice first

    first = _answer(issuer, sid, challenge).json()
    assert first["result"] == "retry" and first["attempts_left"] == MAX_VOICE_ATTEMPTS - 1
    assert len(first["challenge"]) == CHALLENGE_LENGTH

    second = _answer(issuer, sid, first["challenge"]).json()
    assert second["result"] == "passkey_required" and second["reason"] == "attempts"
    assert _answer(issuer, sid, first["challenge"]).status_code == 409    # no third voice attempt
    assert _identify(issuer, sid)["mode"] == "passkey"                    # never a dead end (§2.4)

    assert pay_with_passkey(issuer, sid, DEVICE["passkey"]).json() == {"result": "verified"}
    assert issuer_db.fetch_one("SELECT method FROM sessions WHERE id = ?", (sid,))["method"] == "passkey"


def test_step_up_purchase_falls_back_to_passkey_only_after_two_failures(issuer, monkeypatch):
    # ADR 5: at or above STEP_UP_AMOUNT, two failed voice attempts end in the
    # passkey alone, the same as any other purchase (never a dead end, §2.4).
    monkeypatch.setattr(approvals.v, "score", lambda embedding, center: 0.0)
    sid = _session(issuer, amount_cents=STEP_UP_AMOUNT)
    first = _answer(issuer, sid, _identify(issuer, sid)["challenge"]).json()
    second = _answer(issuer, sid, first["challenge"]).json()
    assert second["result"] == "passkey_required" and second["reason"] == "attempts"
    assert pay_with_passkey(issuer, sid, DEVICE["passkey"]).json() == {"result": "verified"}
    assert issuer_db.fetch_one("SELECT method FROM sessions WHERE id = ?", (sid,))["method"] == "passkey"


def test_replayed_enrollment_audio_fails(issuer):
    sid = _session(issuer)
    challenge = _identify(issuer, sid)["challenge"]
    stolen = wav(take(challenge[0], seed=0))                          # byte-identical to enrollment take 0
    res = _answer(issuer, sid, challenge, **{challenge[0]: stolen}).json()
    assert res["takes"][0]["replay"] is True and res["takes"][0]["passed"] is False
    assert res["result"] == "retry"


def test_too_short_take_is_a_retake_not_a_failed_attempt(issuer):
    sid = _session(issuer)
    challenge = _identify(issuer, sid)["challenge"]
    short = wav(take(challenge[0], seed=5, seconds=0.5))
    res = _answer(issuer, sid, challenge, **{challenge[0]: short})
    assert res.status_code == 422 and "Hold the sound a little longer" in res.json()["detail"]
    assert _identify(issuer, sid)["attempts_left"] == MAX_VOICE_ATTEMPTS


def test_step_up_needs_voice_and_passkey(issuer):
    sid = _session(issuer, amount_cents=STEP_UP_AMOUNT)
    ident = _identify(issuer, sid)
    assert ident["step_up"] is True and ident["mode"] == "voice"
    res = _answer(issuer, sid, ident["challenge"]).json()
    assert res["result"] == "passkey_required" and res["reason"] == "step_up"
    assert _approve(issuer, sid)["verified"] is False                     # voice alone is not enough
    assert pay_with_passkey(issuer, sid, DEVICE["passkey"]).json() == {"result": "verified"}
    assert issuer_db.fetch_one("SELECT method FROM sessions WHERE id = ?", (sid,))["method"] == "voice+passkey"


def test_low_confidence_sound_means_passkey(issuer):
    with issuer_db.transaction() as conn:
        conn.execute("UPDATE templates SET low_confidence = 1 WHERE user_id = ? AND label = 'high'", (USER_ID,))
    try:
        sid = _session(issuer)
        ident = _identify(issuer, sid)
        assert ident["mode"] == "passkey" and ident["reason"] == "not_enrolled"
    finally:
        with issuer_db.transaction() as conn:
            conn.execute("UPDATE templates SET low_confidence = 0 WHERE user_id = ?", (USER_ID,))


def _other_card():
    with issuer_db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO users VALUES ('other-card', 'Other', '2026-01-01T00:00:00+00:00')")
        conn.execute(
            "INSERT INTO payment_tokens (user_id, token_value, last_four, nickname, created_at)"
            " SELECT 'other-card', 'fake_tok_other', '4444', 'MC', '2026-01-01T00:00:00+00:00'"
            " WHERE NOT EXISTS (SELECT 1 FROM payment_tokens WHERE user_id = 'other-card')")


def test_switching_cards_is_refused_even_before_any_attempt(issuer):
    # Security review: bouncing to another card and back re-rolled the
    # challenge for free. A payment now stays with the first card chosen.
    _other_card()
    sid = _session(issuer)
    first = _identify(issuer, sid)["challenge"]
    assert issuer.post(f"/v1/sessions/{sid}/identify", json={"user_id": "other-card"}).status_code == 409
    assert _identify(issuer, sid)["challenge"] == first


def test_simultaneous_guesses_each_use_an_attempt(issuer, monkeypatch):
    # Security review: attempts were counted after scoring, so guesses fired
    # together were all scored but only one counted. Now each claims first.
    sid = _session(issuer)
    challenge = _identify(issuer, sid)["challenge"]
    inner = {}

    def score_and_fire_a_second_guess(embedding, center):
        if "res" not in inner:
            inner["res"] = "pending"
            # Arrives while the first guess is being scored.
            fresh = issuer_db.fetch_one("SELECT labels_json FROM sessions WHERE id = ?", (sid,))["labels_json"]
            inner["res"] = _answer(issuer, sid, json.loads(fresh), seed=500)
        return 0.0

    monkeypatch.setattr(approvals.v, "score", score_and_fire_a_second_guess)
    first = _answer(issuer, sid, challenge)
    counted = issuer_db.fetch_one("SELECT attempts FROM sessions WHERE id = ?", (sid,))["attempts"]
    assert counted == 2, (first.json(), inner["res"].status_code)          # both guesses were paid for
    assert _identify(issuer, sid)["mode"] == "passkey"


# --- Adaptation (§7.4) --------------------------------------------------------

def _centroids():
    return {r["label"]: r["centroid"] for r in issuer_db.fetch_all(
        "SELECT label, centroid FROM templates WHERE user_id = ?", (USER_ID,))}


def test_confident_match_adapts_only_the_challenged_sounds(issuer, monkeypatch):
    monkeypatch.setattr(approvals.v, "score", lambda embedding, center: 0.99)   # confidently above any threshold
    before = _centroids()
    sid = _session(issuer)
    challenge = _identify(issuer, sid)["challenge"]
    assert _answer(issuer, sid, challenge).json()["result"] == "verified"
    after = _centroids()
    for label in SOUNDS:
        assert (after[label] != before[label]) == (label in challenge), label
    drifts = [r["drift"] for r in issuer_db.fetch_all("SELECT drift FROM verifications WHERE session_id = ?", (sid,))]
    assert len(drifts) == CHALLENGE_LENGTH and all(0 < d <= MAX_DRIFT for d in drifts)


def test_borderline_or_failed_attempts_never_adapt(issuer, monkeypatch):
    monkeypatch.setattr(approvals.v, "CONFIDENT_MARGIN", 1.0)   # no pass can be confident
    before = _centroids()
    sid = _session(issuer)
    challenge = _identify(issuer, sid)["challenge"]
    assert _answer(issuer, sid, challenge).json()["result"] == "verified"
    monkeypatch.setattr(approvals.v, "CONFIDENT_MARGIN", 0.0)
    monkeypatch.setattr(approvals.v, "score", lambda embedding, center: 0.0)   # a failing attempt
    failed = _session(issuer)
    assert _answer(issuer, failed, _identify(issuer, failed)["challenge"]).json()["result"] == "retry"
    assert _centroids() == before
    rows = issuer_db.fetch_all("SELECT drift FROM verifications WHERE session_id IN (?, ?)", (sid, failed))
    assert rows and all(r["drift"] is None for r in rows)
