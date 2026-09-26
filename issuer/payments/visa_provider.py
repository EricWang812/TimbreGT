"""Visa PaymentProvider: CyberSource, Visa's payment gateway, in its sandbox
(docs/ALGORITHM.md §9, docs/DECISIONS.md ADR 13).

Visa Intelligent Commerce is gated (§9.1), so this is the Visa rail we can
actually run: CyberSource REST payments against apitest.cybersource.com,
authenticated with HTTP Signature (HMAC-SHA256 over host, date,
request-target, digest, and v-c-merchant-id, keyed by the base64-decoded
shared secret).

Cards are CyberSource customer tokens created in the Business Center from a
Visa test card. create_token() takes that customer token ID, never a card
number, and reads the last four digits back from Token Management; the
stored reference is "cybs:<customer id>" (non-negotiable §2.2).

authorize() places an authorization; the handle it returns is
"<payment id>:<amount cents>", because a CyberSource capture or reversal
must repeat the amount. capture() completes it and reverses the
authorization if capture fails, so no hold is left open. Network and
authentication errors are raised, not converted to declines: the caller
releases the payment claim and the failure is visible.

Refuses any host but the sandbox: Timbre never moves real money.
"""
import base64
import hashlib
import hmac
import json
import logging
from email.utils import formatdate

import httpx

from issuer.payments.base import AuthResult, CaptureResult, PaymentProvider, TokenRef

log = logging.getLogger(__name__)

SANDBOX_HOST = "apitest.cybersource.com"
TOKEN_PREFIX = "cybs:"
CURRENCY = "USD"
CAPTURED = {"PENDING", "TRANSMITTED"}   # a capture accepted for settlement
CARD_TYPES = {"001": "Visa", "002": "Mastercard", "003": "American Express", "004": "Discover"}


class CyberSourceError(RuntimeError):
    """The gateway could not be reached, or refused our credentials."""


def _amount(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


class VisaProvider(PaymentProvider):
    def __init__(self, merchant_id: str, key_id: str, secret_key: str, host: str = SANDBOX_HOST,
                 timeout_s: float = 20.0, transport: httpx.BaseTransport | None = None):
        if host != SANDBOX_HOST:
            raise RuntimeError(f"CyberSource host must be the sandbox ({SANDBOX_HOST}); Timbre never uses production")
        if not (merchant_id and key_id and secret_key):
            raise RuntimeError("PAYMENT_PROVIDER=visa needs CYBERSOURCE_MERCHANT_ID, CYBERSOURCE_KEY_ID, "
                               "and CYBERSOURCE_SECRET_KEY in .env")
        self._merchant_id = merchant_id
        self._key_id = key_id
        self._secret = base64.b64decode(secret_key)
        self._host = host
        self._http = httpx.Client(base_url=f"https://{host}", timeout=timeout_s, transport=transport)

    # --- PaymentProvider -----------------------------------------------------

    def create_token(self, user_id: str, test_card: str) -> TokenRef:
        """`test_card` is a CyberSource customer token ID, not a card number."""
        customer_id = test_card.removeprefix(TOKEN_PREFIX)
        status, body = self._request("GET", f"/tms/v2/customers/{customer_id}/payment-instruments")
        if status != 200:
            raise CyberSourceError(f"customer token for {user_id} not found ({status})")
        instruments = body.get("_embedded", {}).get("paymentInstruments", [])
        if not instruments:
            raise CyberSourceError(f"customer token for {user_id} has no card on it")
        chosen = next((i for i in instruments if i.get("default")), instruments[0])
        identifier = chosen.get("_embedded", {}).get("instrumentIdentifier", {}).get("card", {})
        masked = identifier.get("number", "")
        if len(masked) < 4 or not masked[-4:].isdigit():
            raise CyberSourceError(f"customer token for {user_id} did not return a masked card number")
        card_type = chosen.get("card", {}).get("type") or identifier.get("type")
        return TokenRef(value=f"{TOKEN_PREFIX}{customer_id}", last_four=masked[-4:],
                        nickname=CARD_TYPES.get(card_type, "Card"))

    def authorize(self, token: TokenRef, amount_cents: int,
                  merchant_id: str, instruction_id: str) -> AuthResult:
        if not token.value.startswith(TOKEN_PREFIX):
            raise CyberSourceError("this card was tokenized by another provider; run `make seed`")
        status, body = self._request("POST", "/pts/v2/payments", {
            # The Payment Instruction (ADR 1): the authorization carries the
            # instruction the shopper confirmed, so it cannot be reused.
            "clientReferenceInformation": {"code": instruction_id},
            "paymentInformation": {"customer": {"id": token.value.removeprefix(TOKEN_PREFIX)}},
            "orderInformation": {"amountDetails": {"totalAmount": _amount(amount_cents), "currency": CURRENCY}},
        })
        if status == 201 and body.get("status") == "AUTHORIZED":
            return AuthResult(ok=True, auth_id=f"{body['id']}:{amount_cents}", decline_reason=None)
        reason = body.get("errorInformation", {}).get("reason") or body.get("status") or f"http {status}"
        log.info("authorization declined for %s at %s: %s", instruction_id, merchant_id, reason)
        return AuthResult(ok=False, auth_id=None, decline_reason=reason.lower())

    def capture(self, auth_id: str) -> CaptureResult:
        payment_id, amount_cents = auth_id.rsplit(":", 1)
        amount = {"amountDetails": {"totalAmount": _amount(int(amount_cents)), "currency": CURRENCY}}
        try:
            status, body = self._request("POST", f"/pts/v2/payments/{payment_id}/captures",
                                         {"orderInformation": amount})
        except (CyberSourceError, httpx.HTTPError) as exc:
            log.error("capture failed for %s: %s; reversing the authorization", payment_id, exc)
            self._reverse(payment_id, amount)
            return CaptureResult(ok=False, transaction_id=None)
        if status != 201 or body.get("status") not in CAPTURED:
            log.error("capture of %s ended in %s %s; reversing the authorization",
                      payment_id, status, body.get("status"))
            self._reverse(payment_id, amount)
            return CaptureResult(ok=False, transaction_id=None)
        return CaptureResult(ok=True, transaction_id=body["id"])

    def report_outcome(self, instruction_id: str, outcome: dict) -> None:
        # CyberSource needs no outcome report; kept for the Visa Intelligent
        # Commerce mapping (commerce signals, docs/DECISIONS.md ADR 1).
        log.info("outcome %s %s", instruction_id, outcome)

    # --- HTTP Signature -------------------------------------------------------

    def _request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else b""
        headers = self._signed_headers(method, path, body if payload is not None else None)
        try:
            response = self._http.request(method, path, content=body or None, headers=headers)
        except httpx.HTTPError as exc:
            raise CyberSourceError(f"CyberSource unreachable: {exc}") from exc
        if response.status_code == 401:
            raise CyberSourceError("CyberSource rejected the credentials (401); check the CYBERSOURCE_* keys")
        if response.status_code >= 500:
            raise CyberSourceError(f"CyberSource server error ({response.status_code})")
        try:
            data = response.json() if response.content else {}
        except ValueError as exc:
            raise CyberSourceError(f"CyberSource returned non-JSON ({response.status_code})") from exc
        return response.status_code, data

    def _signed_headers(self, method: str, path: str, body: bytes | None) -> dict:
        date = formatdate(usegmt=True)   # RFC 1123, GMT
        fields = [("host", self._host), ("date", date), ("request-target", f"{method.lower()} {path}")]
        headers = {"host": self._host, "date": date, "v-c-merchant-id": self._merchant_id}
        if body is not None:
            digest = "SHA-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode()
            fields.append(("digest", digest))
            headers["digest"] = digest
            headers["content-type"] = "application/json"
        fields.append(("v-c-merchant-id", self._merchant_id))
        signing = "\n".join(f"{name}: {value}" for name, value in fields)
        signature = base64.b64encode(hmac.new(self._secret, signing.encode(), hashlib.sha256).digest()).decode()
        headers["signature"] = (f'keyid="{self._key_id}", algorithm="HmacSHA256", '
                                f'headers="{" ".join(name for name, _ in fields)}", signature="{signature}"')
        return headers

    def _reverse(self, payment_id: str, amount: dict) -> None:
        try:
            status, body = self._request("POST", f"/pts/v2/payments/{payment_id}/reversals",
                                         {"reversalInformation": {**amount, "reason": "capture failed"}})
            if status != 201 or body.get("status") != "REVERSED":
                log.error("reversal of %s ended in %s %s; it will expire on its own",
                          payment_id, status, body.get("status"))
        except (CyberSourceError, httpx.HTTPError) as exc:
            log.error("could not reverse authorization %s; it will expire on its own: %s", payment_id, exc)
