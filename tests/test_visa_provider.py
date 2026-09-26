"""CyberSource (Visa) provider against a mocked sandbox (ADR 13).

The mock checks each request's HTTP Signature the way CyberSource does, so a
signing mistake fails here rather than as a 401 on stage. No card number
appears anywhere: cards are customer token IDs, and the gateway only ever
returns a masked number (non-negotiable §2.2).
"""
import base64
import hashlib
import hmac
import json
import re

import httpx
import pytest

from issuer import payments
from issuer.payments.base import TokenRef

MERCHANT = "timbre_test"
KEY_ID = "key-123"
SECRET = base64.b64encode(b"sandbox shared secret").decode()
CUSTOMER = "B21E6717A6F03479E05341588E0A303F"


@pytest.fixture(autouse=True)
def visa_selected(monkeypatch):
    # Reached only through get_provider(), like every other caller (§6).
    monkeypatch.setattr(payments, "PAYMENT_PROVIDER", "visa")
    monkeypatch.setattr(payments, "CYBERSOURCE_MERCHANT_ID", MERCHANT)
    monkeypatch.setattr(payments, "CYBERSOURCE_KEY_ID", KEY_ID)
    monkeypatch.setattr(payments, "CYBERSOURCE_SECRET_KEY", SECRET)


def _verify_signature(request: httpx.Request) -> None:
    params = dict(re.findall(r'(\w+)="([^"]*)"', request.headers["signature"]))
    assert params["keyid"] == KEY_ID and params["algorithm"] == "HmacSHA256"
    values = {"host": request.headers["host"], "date": request.headers["date"],
              "request-target": f"{request.method.lower()} {request.url.path}",
              "v-c-merchant-id": request.headers["v-c-merchant-id"]}
    if request.content:
        expected_digest = "SHA-256=" + base64.b64encode(hashlib.sha256(request.content).digest()).decode()
        assert request.headers["digest"] == expected_digest
        values["digest"] = expected_digest
    names = params["headers"].split()
    signing = "\n".join(f"{name}: {values[name]}" for name in names)
    expected = base64.b64encode(hmac.new(base64.b64decode(SECRET), signing.encode(), hashlib.sha256).digest()).decode()
    assert params["signature"] == expected
    assert names[:3] == ["host", "date", "request-target"] and names[-1] == "v-c-merchant-id"


def _provider(routes: dict, calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "apitest.cybersource.com"
        _verify_signature(request)
        calls.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        status, body = routes[(request.method, request.url.path)]
        return httpx.Response(status, json=body)
    return payments.get_provider(transport=httpx.MockTransport(handler))


def test_tokenizes_from_a_customer_token_and_reads_only_the_last_four():
    calls = []
    provider = _provider({("GET", f"/tms/v2/customers/{CUSTOMER}/payment-instruments"): (200, {
        "_embedded": {"paymentInstruments": [{
            "default": True, "card": {"type": "001"},
            "_embedded": {"instrumentIdentifier": {"card": {"number": "411111XXXXXX1111"}}},
        }]}})}, calls)
    token = provider.create_token("maya", CUSTOMER)
    assert token == TokenRef(value=f"cybs:customer:{CUSTOMER}", last_four="1111", nickname="Visa")


def test_a_payment_instrument_token_works_too():
    # Live sandbox: the Business Center handed out payment instrument tokens,
    # and the gateway reports the card type by name ("mastercard").
    calls = []
    provider = _provider({
        ("GET", f"/tms/v2/customers/{CUSTOMER}/payment-instruments"): (404, {"errors": [{"type": "notFound"}]}),
        ("GET", f"/tms/v1/paymentinstruments/{CUSTOMER}"): (200, {
            "card": {"type": "mastercard"},
            "_embedded": {"instrumentIdentifier": {"card": {"number": "555555XXXXXX4444"}}}}),
        ("POST", "/pts/v2/payments"): (201, {"id": "pay_9", "status": "AUTHORIZED"}),
    }, calls)
    token = provider.create_token("jordan", CUSTOMER)
    assert token == TokenRef(value=f"cybs:instrument:{CUSTOMER}", last_four="4444", nickname="Mastercard")
    assert provider.authorize(token, 100, "seaside-market", "instr-9").ok
    assert calls[-1][2]["paymentInformation"] == {"paymentInstrument": {"id": CUSTOMER}}


def test_authorizes_then_captures_with_the_instruction_bound():
    calls = []
    provider = _provider({
        ("POST", "/pts/v2/payments"): (201, {"id": "pay_1", "status": "AUTHORIZED"}),
        ("POST", "/pts/v2/payments/pay_1/captures"): (201, {"id": "cap_1", "status": "PENDING"}),
    }, calls)
    token = TokenRef(value=f"cybs:customer:{CUSTOMER}", last_four="1111", nickname="Visa")

    auth = provider.authorize(token, 5234, "seaside-market", "instr-42")
    assert auth.ok and auth.auth_id == "pay_1:5234"
    assert calls[0][2] == {
        "clientReferenceInformation": {"code": "instr-42"},
        "paymentInformation": {"customer": {"id": CUSTOMER}},
        "orderInformation": {"amountDetails": {"totalAmount": "52.34", "currency": "USD"}},
    }
    captured = provider.capture(auth.auth_id)
    assert captured.ok and captured.transaction_id == "cap_1"
    assert calls[1][2] == {"orderInformation": {"amountDetails": {"totalAmount": "52.34", "currency": "USD"}}}


def test_a_decline_is_a_result_and_bad_credentials_are_an_error():
    token = TokenRef(value=f"cybs:customer:{CUSTOMER}", last_four="1111", nickname="Visa")
    declined = _provider({("POST", "/pts/v2/payments"): (201, {
        "id": "pay_2", "status": "DECLINED", "errorInformation": {"reason": "INSUFFICIENT_FUND"}})}, [])
    result = declined.authorize(token, 100, "seaside-market", "instr-1")
    assert not result.ok and result.decline_reason == "insufficient_fund"

    refused = _provider({("POST", "/pts/v2/payments"): (401, {"response": {"rmsg": "Authentication Failed"}})}, [])
    with pytest.raises(RuntimeError, match="credentials"):
        refused.authorize(token, 100, "seaside-market", "instr-1")


def test_a_failed_capture_reverses_the_hold():
    calls = []
    provider = _provider({
        ("POST", "/pts/v2/payments/pay_3/captures"): (400, {"status": "INVALID_REQUEST"}),
        ("POST", "/pts/v2/payments/pay_3/reversals"): (201, {"id": "rev_3", "status": "REVERSED"}),
    }, calls)
    result = provider.capture("pay_3:999")
    assert not result.ok
    assert calls[-1] == ("POST", "/pts/v2/payments/pay_3/reversals", {
        "reversalInformation": {"amountDetails": {"totalAmount": "9.99", "currency": "USD"}, "reason": "capture failed"}})


def test_refuses_production_and_cards_from_another_provider(monkeypatch):
    provider = _provider({}, [])
    with pytest.raises(RuntimeError, match="make seed"):
        provider.authorize(TokenRef(value="cus_1:pm_1", last_four="4242", nickname="Visa"), 100, "m", "i")
    assert payments.token_is_current("cybs:abc") and not payments.token_is_current("cus_1:pm_1")

    monkeypatch.setattr(payments, "CYBERSOURCE_HOST", "api.cybersource.com")
    with pytest.raises(RuntimeError, match="sandbox"):
        payments.get_provider()
    monkeypatch.setattr(payments, "CYBERSOURCE_HOST", "apitest.cybersource.com")
    monkeypatch.setattr(payments, "CYBERSOURCE_MERCHANT_ID", "")
    with pytest.raises(RuntimeError, match="CYBERSOURCE_MERCHANT_ID"):
        payments.get_provider()
