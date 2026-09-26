"""A minimal software WebAuthn authenticator, for tests only.

Produces real registration and assertion responses (CBOR attestation object,
authenticator data, ECDSA P-256 signatures) in the JSON shape a browser
sends, so issuer/webauthn_routes.py is tested against genuine cryptography
rather than a mock of it.
"""
import base64
import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from issuer.config import WEB_ORIGIN, WEBAUTHN_RP_ID

FLAG_UP, FLAG_UV, FLAG_AT = 0x01, 0x04, 0x40


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SoftAuthenticator:
    def __init__(self, rp_id: str = WEBAUTHN_RP_ID, origin: str = WEB_ORIGIN):
        self.rp_id, self.origin = rp_id, origin
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(16)
        self.sign_count = 0

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin,
                           "crossOrigin": False}).encode()

    def _cose_key(self) -> bytes:
        nums = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"), -3: nums.y.to_bytes(32, "big")})

    def register(self, options: dict) -> dict:
        client_data = self._client_data("webauthn.create", options["challenge"])
        auth_data = (hashlib.sha256(self.rp_id.encode()).digest() + bytes([FLAG_UP | FLAG_UV | FLAG_AT])
                     + struct.pack(">I", self.sign_count) + bytes(16)
                     + struct.pack(">H", len(self.credential_id)) + self.credential_id + self._cose_key())
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64url(self.credential_id), "rawId": b64url(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64url(client_data), "attestationObject": b64url(attestation),
                         "transports": ["internal"]},
            "clientExtensionResults": {}, "authenticatorAttachment": "platform",
        }

    def assert_(self, options: dict) -> dict:
        client_data = self._client_data("webauthn.get", options["challenge"])
        self.sign_count += 1
        auth_data = (hashlib.sha256(self.rp_id.encode()).digest() + bytes([FLAG_UP | FLAG_UV])
                     + struct.pack(">I", self.sign_count))
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64url(self.credential_id), "rawId": b64url(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64url(client_data), "authenticatorData": b64url(auth_data),
                         "signature": b64url(signature), "userHandle": None},
            "clientExtensionResults": {}, "authenticatorAttachment": "platform",
        }


def register(client, user_id: str) -> SoftAuthenticator:
    """Register a fresh soft authenticator for a cardholder through the API."""
    device = SoftAuthenticator()
    options = client.post(f"/v1/passkeys/{user_id}/register/options").json()
    res = client.post(f"/v1/passkeys/{user_id}/register/verify", json={"credential": device.register(options)})
    assert res.status_code == 200, res.text
    return device


def pay_with_passkey(client, session_id: str, device: SoftAuthenticator):
    options = client.post(f"/v1/sessions/{session_id}/passkey/options")
    if options.status_code != 200:
        return options
    return client.post(f"/v1/sessions/{session_id}/passkey",
                       json={"credential": device.assert_(options.json())})
