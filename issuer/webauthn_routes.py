"""Passkeys (WebAuthn): the §7.6 fallback when voice cannot be used.

    GET  /v1/passkeys/{user_id}                    how many passkeys the cardholder has
    POST /v1/passkeys/{user_id}/register/options   creation options for the browser
    POST /v1/passkeys/{user_id}/register/verify    verify and store the new credential

Authentication at checkout is in issuer/approvals.py, using auth_options()
and verify_assertion() below.

RP ID and origin come from .env (WEBAUTHN_RP_ID=localhost,
WEBAUTHN_ORIGIN=http://localhost:5173). The page runs on :5173 and this
service on :8100; the credential is bound to the page origin, which is what
is verified here (docs/CONTEXT.md §12).

Challenges are single-use: each is deleted when taken, before verification,
so a failed attempt cannot be retried against the same challenge.

# STUB: registration has no authentication, like enrollment. In a real
# deployment it sits behind the bank's own login (CLAUDE.md §1.1).
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from issuer.config import (
    WEB_ORIGIN,
    WEBAUTHN_CHALLENGE_TTL_SECONDS,
    WEBAUTHN_RP_ID,
    WEBAUTHN_RP_NAME,
    WEBAUTHN_TIMEOUT_MS,
)
from issuer.db import fetch_all, fetch_one, transaction

log = logging.getLogger(__name__)
router = APIRouter()

# User verification (a PIN or biometric) is preferred, not required: some
# people cannot use a fingerprint reader or type a PIN. Presence of the
# registered device is always required.
USER_VERIFICATION = UserVerificationRequirement.PREFERRED


class CredentialBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: dict


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _store_challenge(key: str, challenge: bytes) -> None:
    expires = (_now() + timedelta(seconds=WEBAUTHN_CHALLENGE_TTL_SECONDS)).isoformat(timespec="seconds")
    with transaction() as conn:
        conn.execute("INSERT OR REPLACE INTO webauthn_challenges (key, challenge, expires_at) VALUES (?, ?, ?)",
                     (key, challenge, expires))


def _take_challenge(key: str) -> bytes:
    """Remove and return the challenge. Committed before verification."""
    with transaction() as conn:
        row = conn.execute("SELECT challenge, expires_at FROM webauthn_challenges WHERE key = ?", (key,)).fetchone()
        conn.execute("DELETE FROM webauthn_challenges WHERE key = ?", (key,))
    if row is None or datetime.fromisoformat(row["expires_at"]) <= _now():
        raise HTTPException(400, "That passkey request expired. Please try again.")
    return row["challenge"]


def _credentials(user_id: str) -> list[PublicKeyCredentialDescriptor]:
    return [PublicKeyCredentialDescriptor(id=r["credential_id"]) for r in fetch_all(
        "SELECT credential_id FROM passkeys WHERE user_id = ? ORDER BY created_at", (user_id,))]


def _require_user(user_id: str) -> dict:
    row = fetch_one("SELECT id, display_name FROM users WHERE id = ?", (user_id,))
    if row is None:
        raise HTTPException(404, "unknown cardholder")
    return dict(row)


@router.get("/v1/passkeys/{user_id}")
def passkey_count(user_id: str) -> dict:
    _require_user(user_id)
    return {"count": len(_credentials(user_id))}


@router.post("/v1/passkeys/{user_id}/register/options")
def register_options(user_id: str) -> dict:
    user = _require_user(user_id)
    options = generate_registration_options(
        rp_id=WEBAUTHN_RP_ID,
        rp_name=WEBAUTHN_RP_NAME,
        user_name=user_id,
        user_id=user_id.encode(),
        user_display_name=user["display_name"],
        timeout=WEBAUTHN_TIMEOUT_MS,
        exclude_credentials=_credentials(user_id),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED, user_verification=USER_VERIFICATION),
    )
    _store_challenge(f"register:{user_id}", options.challenge)
    return json.loads(options_to_json(options))


@router.post("/v1/passkeys/{user_id}/register/verify")
def register_verify(user_id: str, body: CredentialBody) -> dict:
    _require_user(user_id)
    challenge = _take_challenge(f"register:{user_id}")
    try:
        verified = verify_registration_response(
            credential=body.credential, expected_challenge=challenge,
            expected_rp_id=WEBAUTHN_RP_ID, expected_origin=WEB_ORIGIN,
        )
    except WebAuthnException as exc:
        log.warning("passkey registration rejected for %s: %s", user_id, exc)
        raise HTTPException(400, "That passkey could not be verified. Please try again.") from exc
    with transaction() as conn:
        conn.execute(
            "INSERT INTO passkeys (credential_id, user_id, public_key, sign_count, created_at) VALUES (?, ?, ?, ?, ?)",
            (verified.credential_id, user_id, verified.credential_public_key, verified.sign_count,
             _now().isoformat(timespec="seconds")),
        )
    return {"registered": True, "count": len(_credentials(user_id))}


# --- Used by the checkout flow in issuer/approvals.py --------------------------

def auth_options(user_id: str, key: str) -> dict | None:
    """Request options for this cardholder's passkeys, or None if they have none."""
    creds = _credentials(user_id)
    if not creds:
        return None
    options = generate_authentication_options(
        rp_id=WEBAUTHN_RP_ID, timeout=WEBAUTHN_TIMEOUT_MS,
        allow_credentials=creds, user_verification=USER_VERIFICATION,
    )
    _store_challenge(key, options.challenge)
    return json.loads(options_to_json(options))


def verify_assertion(user_id: str, key: str, credential: dict) -> None:
    """Verify a passkey assertion for this cardholder, or raise 400. Updates
    the signature counter, so a replayed assertion fails the next time."""
    challenge = _take_challenge(key)
    raw_id = credential.get("rawId") or credential.get("id")
    if not isinstance(raw_id, str):
        raise HTTPException(400, "That passkey response was incomplete. Please try again.")
    try:
        credential_id = base64url_to_bytes(raw_id)
    except ValueError as exc:
        raise HTTPException(400, "That passkey response was incomplete. Please try again.") from exc
    row = fetch_one("SELECT public_key, sign_count FROM passkeys WHERE credential_id = ? AND user_id = ?",
                    (credential_id, user_id))
    if row is None:
        raise HTTPException(400, "That passkey is not registered for this card.")
    try:
        verified = verify_authentication_response(
            credential=credential, expected_challenge=challenge,
            expected_rp_id=WEBAUTHN_RP_ID, expected_origin=WEB_ORIGIN,
            credential_public_key=row["public_key"], credential_current_sign_count=row["sign_count"],
        )
    except WebAuthnException as exc:
        log.warning("passkey assertion rejected for %s: %s", user_id, exc)
        raise HTTPException(400, "That passkey could not be verified. Please try again.") from exc
    with transaction() as conn:
        conn.execute("UPDATE passkeys SET sign_count = ? WHERE credential_id = ?",
                     (verified.new_sign_count, credential_id))
