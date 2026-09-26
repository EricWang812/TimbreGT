"""Voice enrollment (docs/ALGORITHM.md §7.2). Browser-facing, used only by the
bank's enrollment screen in web/src/issuer/.

    GET    /v1/enroll/{user_id}                           progress for each sound
    POST   /v1/enroll/{user_id}/samples                   one recording (form: label, audio WAV)
    POST   /v1/enroll/{user_id}/labels/{label}/finalize   build the template for a sound
    DELETE /v1/enroll/{user_id}/labels/{label}            start that sound over

Enrollment never dead-ends (non-negotiable §2.4): low cohesion earns one
guided re-record, and after that the sound is accepted as low_confidence.

# STUB: no authentication. In a real deployment this screen lives inside the
# bank's own app, behind its login (CLAUDE.md §1.1). Here only the seeded
# demo cardholders exist.
"""
import logging
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from issuer import verification as v
from issuer.config import (
    COHESION_MIN,
    ENROLL_RERECORD_LIMIT,
    LABELS_PER_USER,
    MAX_DURATION,
    MAX_LABEL_LENGTH,
    RECORDINGS_PER_LABEL,
    SAMPLE_RATE,
)
from issuer.db import fetch_all, fetch_one, transaction
from ml.encoder import embed

log = logging.getLogger(__name__)
router = APIRouter()

# Largest acceptable upload: MAX_DURATION of 32-bit mono audio plus a WAV header.
# This bounds what we decode and embed. It is not a denial-of-service guard:
# the multipart parser has already received the whole body by the time the
# handler runs. Out of scope for the demo (CLAUDE.md §3.4, no hardening).
MAX_UPLOAD_BYTES = int(MAX_DURATION * SAMPLE_RATE * 4) + 4096

RERECORD_MESSAGE = ("These recordings sounded quite different from each other. "
                    "Let's record this sound once more; try to make it the same way each time.")
LOW_CONFIDENCE_MESSAGE = ("Saved. This sound varied between recordings, so your bank will also "
                          "ask for your passkey when this sound is used.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_user(user_id: str) -> dict:
    row = fetch_one("SELECT id, display_name FROM users WHERE id = ?", (user_id,))
    if row is None:
        raise HTTPException(404, "unknown cardholder")
    return dict(row)


def _clean_label(label: str) -> str:
    label = label.strip()
    if not 1 <= len(label) <= MAX_LABEL_LENGTH:
        raise HTTPException(422, f"Give the sound a name of 1 to {MAX_LABEL_LENGTH} characters.")
    return label


def _progress(user_id: str) -> dict:
    user = _require_user(user_id)
    labels = []
    for row in fetch_all(
        "SELECT l.label, l.rerecords, t.low_confidence,"
        " (SELECT COUNT(*) FROM enroll_samples s WHERE s.user_id = l.user_id AND s.label = l.label) AS samples"
        " FROM enroll_labels l LEFT JOIN templates t ON t.user_id = l.user_id AND t.label = l.label"
        " WHERE l.user_id = ? ORDER BY l.created_at, l.label",
        (user_id,),
    ):
        if row["low_confidence"] is None:
            status = "collecting"
        else:
            status = "low_confidence" if row["low_confidence"] else "enrolled"
        labels.append({
            "label": row["label"],
            "status": status,
            "samples": row["samples"],
            "rerecords_left": ENROLL_RERECORD_LIMIT - row["rerecords"],
        })
    return {
        "user_id": user["id"],
        "display_name": user["display_name"],
        "labels": labels,
        "labels_needed": LABELS_PER_USER,
        "recordings_per_label": RECORDINGS_PER_LABEL,
    }


@router.get("/v1/enroll/{user_id}")
def get_progress(user_id: str) -> dict:
    return _progress(user_id)


@router.post("/v1/enroll/{user_id}/samples")
def add_sample(user_id: str, label: str = Form(...), audio: UploadFile = File(...)) -> dict:
    _require_user(user_id)
    label = _clean_label(label)
    data = audio.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Keep each recording under {MAX_DURATION:g} seconds.")
    try:
        waveform = v.decode_upload(data)
        v.check_recording(waveform)
    except v.RecordingRejected as exc:
        raise HTTPException(422, str(exc)) from exc

    vector = embed(waveform, SAMPLE_RATE)  # outside the write lock: ~150 ms of CPU

    with transaction() as conn:
        existing = {r["label"] for r in conn.execute(
            "SELECT label FROM enroll_labels WHERE user_id = ?", (user_id,))}
        if label not in existing:
            if len(existing) >= LABELS_PER_USER:
                raise HTTPException(409, f"You already have {LABELS_PER_USER} sounds. Start one over to change it.")
            conn.execute("INSERT INTO enroll_labels (user_id, label, created_at) VALUES (?, ?, ?)",
                         (user_id, label, _now()))
        if conn.execute("SELECT 1 FROM templates WHERE user_id = ? AND label = ?", (user_id, label)).fetchone():
            raise HTTPException(409, f'"{label}" is already set up. Start it over to record it again.')
        count = conn.execute("SELECT COUNT(*) FROM enroll_samples WHERE user_id = ? AND label = ?",
                             (user_id, label)).fetchone()[0]
        if count >= RECORDINGS_PER_LABEL:
            raise HTTPException(409, f'"{label}" already has {RECORDINGS_PER_LABEL} recordings.')
        conn.execute(
            "INSERT INTO enroll_samples (user_id, label, waveform, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, label, waveform.astype(np.float32).tobytes(), vector.tobytes(), _now()),
        )
    return {"label": label, "samples": count + 1, "needed": RECORDINGS_PER_LABEL}


@router.post("/v1/enroll/{user_id}/labels/{label}/finalize")
def finalize(user_id: str, label: str) -> dict:
    _require_user(user_id)
    # One write transaction for the whole read-decide-write, so a double-clicked
    # finalize or a concurrent start-over cannot both act on the same stale read
    # (e.g. taking the re-record branch twice). The math is a few microseconds
    # on 5 x 192 floats, so holding the lock for it costs nothing.
    with transaction() as conn:
        state = conn.execute("SELECT rerecords FROM enroll_labels WHERE user_id = ? AND label = ?",
                             (user_id, label)).fetchone()
        if state is None:
            raise HTTPException(404, f'There is no sound called "{label}".')
        rows = conn.execute("SELECT embedding FROM enroll_samples WHERE user_id = ? AND label = ? ORDER BY id",
                            (user_id, label)).fetchall()
        if len(rows) != RECORDINGS_PER_LABEL:
            raise HTTPException(409, f'"{label}" needs {RECORDINGS_PER_LABEL} recordings; it has {len(rows)}.')
        embeddings = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
        score = v.cohesion(embeddings)

        if score < COHESION_MIN and state["rerecords"] < ENROLL_RERECORD_LIMIT:
            conn.execute("DELETE FROM enroll_samples WHERE user_id = ? AND label = ?", (user_id, label))
            conn.execute("UPDATE enroll_labels SET rerecords = rerecords + 1 WHERE user_id = ? AND label = ?",
                         (user_id, label))
            rerecord = True
        else:
            rerecord = False
            center = v.centroid(embeddings)
            template_spread = v.spread(embeddings)
            low_confidence = score < COHESION_MIN
            conn.execute(
                "INSERT OR REPLACE INTO templates"
                " (user_id, label, centroid, spread, cohesion, low_confidence, n_samples, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, label, center.tobytes(), template_spread, score, int(low_confidence), len(rows), _now()),
            )

    if rerecord:
        log.info("enrollment re-record: user=%s label=%r cohesion=%.3f", user_id, label, score)
        return {"status": "rerecord", "message": RERECORD_MESSAGE, "cohesion": round(score, 3)}
    if low_confidence:
        # §7.2: a person who cannot enroll cleanly is a finding to report, not an error to hide.
        log.warning("enrollment accepted as low_confidence: user=%s label=%r cohesion=%.3f",
                    user_id, label, score)
    return {
        "status": "low_confidence" if low_confidence else "enrolled",
        "message": LOW_CONFIDENCE_MESSAGE if low_confidence else "Saved.",
        "cohesion": round(score, 3),
        "spread": round(template_spread, 3),
        "threshold": round(v.personal_threshold(template_spread), 3),
    }


@router.delete("/v1/enroll/{user_id}/labels/{label}")
def start_over(user_id: str, label: str) -> dict:
    _require_user(user_id)
    with transaction() as conn:
        for table in ("enroll_samples", "templates", "enroll_labels"):
            conn.execute(f"DELETE FROM {table} WHERE user_id = ? AND label = ?", (user_id, label))
    return _progress(user_id)
