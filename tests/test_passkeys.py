"""Passkeys (issuer/webauthn_routes.py), exercised with a software
authenticator that produces real WebAuthn responses (tests/softauthn.py)."""
import copy
import uuid

import pytest
from fastapi.testclient import TestClient

from issuer import db as issuer_db
from issuer.main import app as issuer_app
from tests.softauthn import SoftAuthenticator, b64url, pay_with_passkey, register


def _cardholder(user_id):
    with issuer_db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, '2026-01-01T00:00:00+00:00')", (user_id, user_id))
        conn.execute(
            "INSERT INTO payment_tokens (user_id, token_value, last_four, nickname, created_at)"
            " SELECT ?, 'fake_tok_pk', '4242', 'Visa', '2026-01-01T00:00:00+00:00'"
            " WHERE NOT EXISTS (SELECT 1 FROM payment_tokens WHERE user_id = ?)", (user_id, user_id))
        conn.execute("DELETE FROM passkeys WHERE user_id = ?", (user_id,))
    return user_id


@pytest.fixture
def issuer():
    with TestClient(issuer_app) as client:
        yield client


def _session_for(client, user_id):
    """A pending payment bound to a cardholder with no voiceprint, so the bank
    asks for the passkey."""
    sid = client.post("/v1/sessions", json={"instruction_id": str(uuid.uuid4()), "amount_cents": 999,
                                            "merchant_id": "test-merchant"}).json()["session_id"]
    assert client.post(f"/v1/sessions/{sid}/identify", json={"user_id": user_id}).json()["mode"] == "passkey"
    return sid


def test_register_then_pay(issuer):
    user = _cardholder("pk-alice")
    device = register(issuer, user)
    assert issuer.get(f"/v1/passkeys/{user}").json() == {"count": 1}
    options = issuer.post(f"/v1/passkeys/{user}/register/options").json()
    assert [c["id"] for c in options["excludeCredentials"]] == [b64url(device.credential_id)]
    assert pay_with_passkey(issuer, _session_for(issuer, user), device).json() == {"result": "verified"}


def test_registration_from_another_origin_is_rejected(issuer):
    user = _cardholder("pk-bob")
    phisher = SoftAuthenticator(origin="https://evil.example")
    options = issuer.post(f"/v1/passkeys/{user}/register/options").json()
    res = issuer.post(f"/v1/passkeys/{user}/register/verify", json={"credential": phisher.register(options)})
    assert res.status_code == 400
    assert issuer.get(f"/v1/passkeys/{user}").json() == {"count": 0}


def test_registration_challenge_is_single_use(issuer):
    user = _cardholder("pk-carol")
    device = SoftAuthenticator()
    options = issuer.post(f"/v1/passkeys/{user}/register/options").json()
    response = device.register(options)
    assert issuer.post(f"/v1/passkeys/{user}/register/verify", json={"credential": response}).status_code == 200
    assert issuer.post(f"/v1/passkeys/{user}/register/verify", json={"credential": response}).status_code == 400


def test_no_passkey_is_routed_not_dead_ended(issuer):
    user = _cardholder("pk-dave")
    res = issuer.post(f"/v1/sessions/{_session_for(issuer, user)}/passkey/options")
    assert res.status_code == 409 and res.json()["detail"] == "no_passkey"


def test_replayed_assertion_is_rejected(issuer):
    user = _cardholder("pk-erin")
    device = register(issuer, user)
    sid = _session_for(issuer, user)
    options = issuer.post(f"/v1/sessions/{sid}/passkey/options").json()
    assertion = device.assert_(options)
    # The same signed response, sent against a fresh challenge, must fail.
    issuer.post(f"/v1/sessions/{sid}/passkey/options")
    assert issuer.post(f"/v1/sessions/{sid}/passkey", json={"credential": assertion}).status_code == 400


def test_cloned_authenticator_is_caught_by_the_signature_counter(issuer):
    user = _cardholder("pk-frank")
    device = register(issuer, user)
    assert pay_with_passkey(issuer, _session_for(issuer, user), device).json() == {"result": "verified"}
    clone = copy.copy(device)
    clone.sign_count = 0                                 # a copied key with an older counter
    assert pay_with_passkey(issuer, _session_for(issuer, user), clone).status_code == 400


def test_another_cards_passkey_is_refused(issuer):
    alice, mallory = _cardholder("pk-grace"), _cardholder("pk-mallory")
    register(issuer, alice)
    mallorys_device = register(issuer, mallory)
    res = pay_with_passkey(issuer, _session_for(issuer, alice), mallorys_device)
    assert res.status_code == 400 and "not registered for this card" in res.json()["detail"]


def test_tampered_signature_is_rejected(issuer):
    user = _cardholder("pk-heidi")
    device = register(issuer, user)
    sid = _session_for(issuer, user)
    assertion = device.assert_(issuer.post(f"/v1/sessions/{sid}/passkey/options").json())
    assertion["response"]["signature"] = b64url(b"\x30\x06\x02\x01\x01\x02\x01\x01")   # a valid-looking, wrong signature
    assert issuer.post(f"/v1/sessions/{sid}/passkey", json={"credential": assertion}).status_code == 400
    assert issuer.get(f"/v1/sessions/{sid}").json()["status"] == "pending"          # nothing charged
