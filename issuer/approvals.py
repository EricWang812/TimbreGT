"""Approval sessions: the issuer half of checkout (docs/DECISIONS.md ADR 2).

Merchant-facing, server to server:
    POST /v1/sessions  {instruction_id, amount_cents, merchant_id} -> {session_id}
    POST /v1/approve   {instruction_id} -> {verified, transaction_id}

Browser-facing, called only by the issuer widget (web/src/issuer/):
    GET  /v1/sessions/{session_id}
    GET  /v1/sessions/{session_id}/cardholders
    POST /v1/sessions/{session_id}/extend
    POST /v1/sessions/{session_id}/identify   {user_id} -> voice challenge or passkey
    POST /v1/sessions/{session_id}/voice      multipart audio x2 -> scores and result
    POST /v1/sessions/{session_id}/passkey/options -> WebAuthn request options
    POST /v1/sessions/{session_id}/passkey    {credential} -> verified passkey, then pay

Session states: pending -> processing -> verified, or back to pending if the
payment fails. pending and processing both expire after SESSION_TTL_SECONDS.

The merchant never sends who the shopper is and never learns how they were
verified. The cardholder is identified inside the issuer widget, the way a
3-D Secure challenge page identifies you, not by anything the merchant says.
"""
import json
import logging
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

import numpy as np
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from issuer import verification as v
from issuer.config import (
    LABELS_PER_USER,
    MAX_VOICE_ATTEMPTS,
    SAMPLE_RATE,
    SESSION_ID_BYTES,
    SESSION_MAX_EXTENSIONS,
    SESSION_TTL_SECONDS,
    STEP_UP_AMOUNT,
)
from issuer.db import fetch_all, fetch_one, transaction
from issuer.enrollment import MAX_UPLOAD_BYTES
from issuer.liveness import is_replay, pick_challenge
from issuer.payments.base import TokenRef
from issuer.webauthn_routes import CredentialBody, auth_options, verify_assertion
from ml.encoder import embed

log = logging.getLogger(__name__)
router = APIRouter()


class CreateSessionRequest(BaseModel):
    # extra="forbid": a merchant that tries to send cardholder identity (or
    # anything else) is rejected with 422 rather than silently ignored.
    model_config = ConfigDict(extra="forbid")
    instruction_id: UUID
    amount_cents: int = Field(gt=0)
    merchant_id: str = Field(min_length=1, max_length=64)


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction_id: UUID


class ApproveResponse(BaseModel):
    """Non-negotiable §2.5: the merchant learns exactly these two fields."""
    verified: bool
    transaction_id: str | None


class IdentifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=64)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _effective_status(row: sqlite3.Row) -> str:
    """Expiry is derived at read time, so no request has to write it back.
    A session stuck in 'processing' (process died mid-payment) expires too,
    so it can never block the shopper forever."""
    if row["status"] in ("pending", "processing") and datetime.fromisoformat(row["expires_at"]) <= _now():
        return "expired"
    return row["status"]


# --- Merchant-facing -------------------------------------------------------

@router.post("/v1/sessions")
def create_session(body: CreateSessionRequest) -> dict:
    session_id = secrets.token_urlsafe(SESSION_ID_BYTES)
    now = _now()
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO sessions (id, instruction_id, amount_cents, merchant_id, status, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, 'pending', ?, ?)",
                (session_id, str(body.instruction_id), body.amount_cents, body.merchant_id,
                 _iso(now), _iso(now + timedelta(seconds=SESSION_TTL_SECONDS))),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, "instruction_id already has a session") from exc
    return {"session_id": session_id}


@router.post("/v1/approve", response_model=ApproveResponse)
def approve(body: ApproveRequest) -> ApproveResponse:
    row = fetch_one(
        "SELECT status, expires_at, transaction_id FROM sessions WHERE instruction_id = ?",
        (str(body.instruction_id),),
    )
    if row is None:
        raise HTTPException(404, "unknown instruction_id")
    verified = _effective_status(row) == "verified"
    return ApproveResponse(verified=verified, transaction_id=row["transaction_id"] if verified else None)


# --- Widget-facing ---------------------------------------------------------

def _require_pending(row: sqlite3.Row | None) -> None:
    if row is None:
        raise HTTPException(404, "unknown session")
    status = _effective_status(row)
    if status == "expired":
        raise HTTPException(410, "session expired")
    if status != "pending":
        raise HTTPException(409, f"session already {status}")


@router.get("/v1/sessions/{session_id}/cardholders")
def list_cardholders(session_id: str) -> list[dict]:
    # Demo harness: stands in for "the cardholder signs in to their bank".
    # Scoped to a live session so the list cannot be browsed outside checkout.
    _require_pending(fetch_one("SELECT status, expires_at FROM sessions WHERE id = ?", (session_id,)))
    rows = fetch_all(
        "SELECT u.id, u.display_name, t.nickname, t.last_four"
        " FROM users u JOIN payment_tokens t ON t.user_id = u.id"
        " ORDER BY u.display_name, t.id"
    )
    return [dict(r) for r in rows]


def _seconds_remaining(row: sqlite3.Row) -> int:
    return max(0, int((datetime.fromisoformat(row["expires_at"]) - _now()).total_seconds()))


@router.get("/v1/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    row = fetch_one(
        "SELECT merchant_id, amount_cents, status, expires_at, extensions FROM sessions WHERE id = ?",
        (session_id,),
    )
    if row is None:
        raise HTTPException(404, "unknown session")
    return {
        "session_id": session_id,
        "merchant_id": row["merchant_id"],
        "amount_cents": row["amount_cents"],
        "status": _effective_status(row),
        "seconds_remaining": _seconds_remaining(row),
        "extensions_left": SESSION_MAX_EXTENSIONS - row["extensions"],
    }


@router.post("/v1/sessions/{session_id}/extend")
def extend_session(session_id: str) -> dict:
    """WCAG 2.2.1 Timing Adjustable: the cardholder can ask for more time,
    at least SESSION_MAX_EXTENSIONS times, before the request expires."""
    with transaction() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        _require_pending(row)
        if row["extensions"] >= SESSION_MAX_EXTENSIONS:
            raise HTTPException(409, "no extensions left")
        expires_at = _iso(_now() + timedelta(seconds=SESSION_TTL_SECONDS))
        conn.execute("UPDATE sessions SET expires_at = ?, extensions = extensions + 1 WHERE id = ?",
                     (expires_at, session_id))
    return {"seconds_remaining": SESSION_TTL_SECONDS,
            "extensions_left": SESSION_MAX_EXTENSIONS - row["extensions"] - 1}


# --- Verification: identify, voice challenge, passkey (§7.5, §7.6) ----------
#
# identify  binds the cardholder and returns what the bank will ask for: two
#           of their sounds in random order, or the passkey when voice is not
#           available (not fully enrolled, a low-confidence sound per §7.2, or
#           MAX_VOICE_ATTEMPTS already used).
# voice     scores both takes; both must pass. At or above STEP_UP_AMOUNT a
#           voice pass still needs the passkey (recorded as method='voice'
#           while the session stays pending).
# passkey   a real WebAuthn assertion (issuer/webauthn_routes.py), allowed only
#           where the flow asks for one.
#
# Scores and thresholds go to the bank's widget only. The merchant still
# learns nothing beyond {verified, transaction_id} (§2.5).

PASSKEY_REASONS = {
    "not_enrolled": "Voice approval is not fully set up for this card, so your bank will use your passkey.",
    "attempts": "Your voice did not match after two tries. Use your passkey to finish.",
    "step_up": "Voice matched. Purchases of this size also need your passkey.",
}


def _usable_labels(user_id: str) -> list[str]:
    return [r["label"] for r in fetch_all(
        "SELECT label FROM templates WHERE user_id = ? AND low_confidence = 0 ORDER BY label", (user_id,))]


def _voice_ready(user_id: str) -> bool:
    """Voice is offered only with a full set of confident sounds: a
    low-confidence sound means passkey until another is enrolled (§7.2)."""
    return len(_usable_labels(user_id)) >= LABELS_PER_USER


def _step_up(session: sqlite3.Row) -> bool:
    return session["amount_cents"] >= STEP_UP_AMOUNT


def _passkey_state(session: sqlite3.Row, reason: str) -> dict:
    return {"mode": "passkey", "reason": reason, "message": PASSKEY_REASONS[reason],
            "challenge": None, "attempts_left": 0, "step_up": _step_up(session)}


@router.post("/v1/sessions/{session_id}/identify")
def identify(session_id: str, body: IdentifyRequest) -> dict:
    if fetch_one("SELECT 1 FROM payment_tokens WHERE user_id = ?", (body.user_id,)) is None:
        raise HTTPException(404, "unknown cardholder")
    voice_ready = _voice_ready(body.user_id)
    with transaction() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        _require_pending(session)
        same_card = session["user_id"] == body.user_id
        if session["user_id"] is not None and not same_card:
            # A payment stays with the first card chosen. Switching away and
            # back would otherwise re-roll the challenge for free, or reset
            # the attempt count. A different card means a new checkout, which
            # the store always offers, so this is not a dead end.
            raise HTTPException(409, "this payment is already being verified for another card; "
                                     "return to the store to pay with a different card")
        attempts = session["attempts"]
        if not voice_ready or attempts >= MAX_VOICE_ATTEMPTS:
            challenge = None
        elif same_card and session["labels_json"]:
            # Keep the challenge already issued: re-identifying must not let
            # anyone re-roll until they get a pair they have recordings of.
            challenge = json.loads(session["labels_json"])
        else:
            challenge = pick_challenge(_usable_labels(body.user_id))
        conn.execute("UPDATE sessions SET user_id = ?, attempts = ?, labels_json = ? WHERE id = ?",
                     (body.user_id, attempts, json.dumps(challenge) if challenge else None, session_id))
    if same_card and session["method"] == "voice":
        return _passkey_state(session, "step_up")
    if not voice_ready:
        return _passkey_state(session, "not_enrolled")
    if challenge is None:
        return _passkey_state(session, "attempts")
    return {"mode": "voice", "challenge": challenge, "attempts_left": MAX_VOICE_ATTEMPTS - attempts,
            "step_up": _step_up(session), "reason": None, "message": None}


@router.post("/v1/sessions/{session_id}/voice")
def voice(session_id: str, request: Request, audio: list[UploadFile] = File(...)) -> dict:
    started = time.perf_counter()
    session = fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    _require_pending(session)
    if session["user_id"] is None or session["labels_json"] is None:
        raise HTTPException(409, "choose your card first")
    if session["method"] == "voice":
        raise HTTPException(409, "voice already matched; finish with your passkey")
    if session["attempts"] >= MAX_VOICE_ATTEMPTS:
        raise HTTPException(409, "no voice attempts left; use your passkey")
    challenge = json.loads(session["labels_json"])
    if len(audio) != len(challenge):
        raise HTTPException(422, f"expected {len(challenge)} recordings, got {len(audio)}")

    # A take that cannot be used (too short, too quiet) is a retake, not a
    # failed verification: it does not use up an attempt.
    waveforms = []
    for i, (label, upload) in enumerate(zip(challenge, audio)):
        data = upload.file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f'Sound {i + 1}, "{label}": keep each recording shorter.')
        try:
            waveform = v.decode_upload(data)
            v.check_recording(waveform)
        except v.RecordingRejected as exc:
            raise HTTPException(422, f'Sound {i + 1}, "{label}": {exc}') from exc
        waveforms.append(waveform)

    # Claim the attempt BEFORE scoring. If it were counted only afterwards,
    # N guesses fired at once would all be scored while only one counted.
    # A matching attempt is refunded below; only failures use up the budget.
    claimed = session["attempts"] + 1
    with transaction() as conn:
        cur = conn.execute(
            "UPDATE sessions SET attempts = ? WHERE id = ? AND status = 'pending' AND attempts = ?"
            " AND labels_json = ? AND method IS NULL",
            (claimed, session_id, session["attempts"], session["labels_json"]),
        )
        if cur.rowcount != 1:
            raise HTTPException(409, "another attempt for this payment is already in progress")

    user_id = session["user_id"]
    templates = {r["label"]: r for r in fetch_all(
        "SELECT label, centroid, spread FROM templates WHERE user_id = ?", (user_id,))}
    stored = [np.frombuffer(r["waveform"], dtype=np.float32) for r in fetch_all(
        "SELECT waveform FROM enroll_samples WHERE user_id = ?", (user_id,))]

    takes, scored = [], []
    for label, waveform in zip(challenge, waveforms):
        template = templates.get(label)
        if template is None:
            raise HTTPException(409, f'"{label}" is no longer set up; choose your card again')
        center = np.frombuffer(template["centroid"], dtype=np.float32)
        embedding = embed(waveform, SAMPLE_RATE)
        take_score = v.score(embedding, center)
        threshold = v.personal_threshold(template["spread"])
        replay = is_replay(waveform, stored)
        takes.append({"label": label, "score": round(take_score, 3), "threshold": round(threshold, 3),
                      "replay": replay, "passed": bool(take_score >= threshold and not replay)})
        scored.append((template["centroid"], center, embedding, threshold))
    matched = all(t["passed"] for t in takes)
    # §7.4: only a matched attempt may adapt, and adapt() itself skips any
    # take that did not clear the threshold by CONFIDENT_MARGIN.
    updates = [v.adapt(center, embedding, threshold) if matched else (center, None)
               for _, center, embedding, threshold in scored]
    latency_ms = round((time.perf_counter() - started) * 1000)

    next_challenge = None
    attempts = claimed
    with transaction() as conn:
        for t, (old_blob, _, _, _), (new_center, drift) in zip(takes, scored, updates):
            if drift is not None:
                # Guarded on the template read above: a concurrent update wins
                # rather than being silently overwritten.
                cur = conn.execute(
                    "UPDATE templates SET centroid = ?, updated_at = ? WHERE user_id = ? AND label = ?"
                    " AND centroid = ?", (new_center.tobytes(), _iso(_now()), user_id, t["label"], old_blob))
                if cur.rowcount != 1:
                    log.warning("template for %s/%s changed during scoring; not adapted", user_id, t["label"])
                    drift = None
            conn.execute(
                "INSERT INTO verifications (session_id, user_id, label, score, threshold, passed, replay,"
                " drift, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, user_id, t["label"], t["score"], t["threshold"], int(t["passed"]),
                 int(t["replay"]), drift, latency_ms, _iso(_now())),
            )
        if not matched:
            if attempts < MAX_VOICE_ATTEMPTS:
                next_challenge = pick_challenge(_usable_labels(user_id))  # a fresh pair for the retry
            # labels_json is only replaced if no concurrent attempt has claimed since.
            conn.execute("UPDATE sessions SET labels_json = ? WHERE id = ? AND attempts = ?",
                         (json.dumps(next_challenge) if next_challenge else None, session_id, claimed))
        else:
            # A match does not use up the budget: refund this attempt.
            attempts = claimed - 1
            method_sql = ", method = 'voice'" if _step_up(session) else ""
            conn.execute(f"UPDATE sessions SET attempts = attempts - 1{method_sql} WHERE id = ?", (session_id,))

    base = {"takes": takes, "latency_ms": latency_ms}
    if not matched:
        log.info("voice attempt failed: session=%s attempt=%d", session_id, attempts)
        if next_challenge is None:
            return {**base, **_passkey_state(session, "attempts"), "result": "passkey_required"}
        return {**base, "result": "retry", "challenge": next_challenge,
                "attempts_left": MAX_VOICE_ATTEMPTS - attempts}
    if _step_up(session):
        return {**base, **_passkey_state(session, "step_up"), "result": "passkey_required"}
    return {**base, "result": _complete_payment(request, session_id, "voice")}


def _passkey_session(session_id: str) -> sqlite3.Row:
    """The session, if the flow is at a point where a passkey is asked for:
    no usable voice, voice attempts used up, or a step-up after a voice pass."""
    session = fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
    _require_pending(session)
    if session["user_id"] is None:
        raise HTTPException(409, "choose your card first")
    allowed = (session["method"] == "voice" or session["attempts"] >= MAX_VOICE_ATTEMPTS
               or not _voice_ready(session["user_id"]))
    if not allowed:
        raise HTTPException(409, "use your voice first")
    return session


@router.post("/v1/sessions/{session_id}/passkey/options")
def passkey_options(session_id: str) -> dict:
    session = _passkey_session(session_id)
    options = auth_options(session["user_id"], f"session:{session_id}")
    if options is None:
        # Not a dead end: the widget offers to set one up in the bank app,
        # and the session stays open (and extendable) meanwhile.
        raise HTTPException(409, "no_passkey")
    return options


@router.post("/v1/sessions/{session_id}/passkey")
def passkey(session_id: str, body: CredentialBody, request: Request) -> dict:
    session = _passkey_session(session_id)
    verify_assertion(session["user_id"], f"session:{session_id}", body.credential)
    method = "voice+passkey" if session["method"] == "voice" else "passkey"
    return {"result": _complete_payment(request, session_id, method)}


def _complete_payment(request: Request, session_id: str, method: str) -> str:
    """Claim, charge, settle. Returns 'verified' or 'payment_failed'."""
    provider = request.app.state.provider

    # 1. Claim the session in a short write transaction. Moving it to
    #    'processing' makes a concurrent completion fail with 409, so the
    #    payment below can run with no database lock held.
    with transaction() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        _require_pending(session)
        token_row = conn.execute(
            "SELECT token_value, last_four, nickname FROM payment_tokens WHERE user_id = ? ORDER BY id LIMIT 1",
            (session["user_id"],),
        ).fetchone()
        if token_row is None:
            raise HTTPException(404, "unknown cardholder")
        conn.execute("UPDATE sessions SET status = 'processing' WHERE id = ?", (session_id,))
    token = TokenRef(value=token_row["token_value"], last_four=token_row["last_four"],
                     nickname=token_row["nickname"])

    # 2. Charge outside any transaction. Any failure, including an exception,
    #    returns the session to 'pending' so the shopper can try again
    #    (non-negotiable §2.4: never dead-end the user).
    try:
        transaction_id = _charge(provider, token, session)
    except Exception:
        _settle(session_id, "pending", None, None)
        raise
    outcome = "verified" if transaction_id else "payment_failed"
    _settle(session_id, "verified" if transaction_id else "pending", transaction_id,
            method if transaction_id else None)
    provider.report_outcome(session["instruction_id"], {"status": outcome})
    return outcome


def _charge(provider, token: TokenRef, session: sqlite3.Row) -> str | None:
    """Authorize then capture. Returns the transaction id, or None on failure."""
    auth = provider.authorize(token, session["amount_cents"], session["merchant_id"], session["instruction_id"])
    if not auth.ok:
        log.warning("authorization declined for session %s: %s", session["id"], auth.decline_reason)
        return None
    capture = provider.capture(auth.auth_id)
    if not capture.ok or not capture.transaction_id:
        # The provider cancels the authorization itself when capture fails
        # (issuer/payments/stripe_provider.py), so no hold is left open.
        log.error("capture failed for session %s (authorization %s)", session["id"], auth.auth_id)
        return None
    return capture.transaction_id


def _settle(session_id: str, status: str, transaction_id: str | None, method: str | None) -> None:
    """Move a claimed session out of 'processing'. Fails loudly if something
    else changed it in the meantime, which should be impossible. A released
    claim keeps the cardholder and any voice pass, so a retry resumes."""
    with transaction() as conn:
        cur = conn.execute(
            "UPDATE sessions SET status = ?, transaction_id = ?, method = COALESCE(?, method)"
            " WHERE id = ? AND status = 'processing'",
            (status, transaction_id, method, session_id),
        )
        if cur.rowcount != 1:
            raise RuntimeError(f"session {session_id} left 'processing' unexpectedly")
