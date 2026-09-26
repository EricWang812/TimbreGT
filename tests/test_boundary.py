"""The merchant/issuer boundary, as tests. Non-negotiable §2.5 in machine form:
if any test here fails, the build is broken regardless of what else works.

The merchant's httpx client is pointed at the issuer app in-process, so these
exercise the real server-to-server path without opening ports.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from api import db as merchant_db
from api import issuer_client
from api.cart import shipping_for, tax_for
from api.config import FREE_SHIPPING_MIN_CENTS, SHIPPING_CENTS
from api.main import app as merchant_app
from issuer import db as issuer_db
from issuer.config import SESSION_MAX_EXTENSIONS, SESSION_TTL_SECONDS
from issuer.main import app as issuer_app
from tests.softauthn import pay_with_passkey, register
from issuer.payments.base import AuthResult, CaptureResult, PaymentProvider

APPROVAL_KEYS = {"verified", "transaction_id"}
# Every header the approval responses may carry, with its only permitted value
# where the value is fixed. `vary: Origin` is added by the CORS middleware as
# a caching directive and says nothing about the purchase.
ALLOWED_HEADERS = {"content-length": None, "content-type": "application/json", "vary": "Origin"}
PRODUCT_ID = "test-apple"
PRICE_CENTS = 250
USER_ID = "test-user"


@pytest.fixture
def clients(monkeypatch):
    with TestClient(issuer_app) as issuer, TestClient(merchant_app) as merchant:
        monkeypatch.setattr(issuer_client, "client", issuer)
        _seed()
        yield merchant, issuer


def _seed():
    with merchant_db.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (PRODUCT_ID, "Test Apple", "Test Farm", "1 lb", "produce", PRICE_CENTS,
             "https://example.invalid/apple.jpg", "test fixture"),
        )
    with issuer_db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO users VALUES (?, 'Test User', '2026-01-01T00:00:00+00:00')",
                     (USER_ID,))
        conn.execute(
            "INSERT INTO payment_tokens (user_id, token_value, last_four, nickname, created_at)"
            " SELECT ?, 'fake_tok_test', '4242', 'Visa', '2026-01-01T00:00:00+00:00'"
            " WHERE NOT EXISTS (SELECT 1 FROM payment_tokens WHERE user_id = ?)",
            (USER_ID, USER_ID),
        )


def _checkout(merchant, quantity=2) -> dict:
    res = merchant.post("/checkout/confirm", json={"items": [{"product_id": PRODUCT_ID, "quantity": quantity}]})
    assert res.status_code == 200, res.text
    return res.json()


def _verify(issuer, session_id, user_id=USER_ID):
    """Complete the bank's side. The seeded test user has no voiceprint, so the
    bank routes them to the passkey (a real WebAuthn assertion from a software
    authenticator); voice is covered in
    tests/test_challenge.py."""
    res = issuer.post(f"/v1/sessions/{session_id}/identify", json={"user_id": user_id})
    if res.status_code != 200:
        return res
    assert res.json()["mode"] == "passkey"
    return pay_with_passkey(issuer, session_id, _device(issuer, user_id))


_DEVICES = {}


def _device(issuer, user_id):
    """One registered soft passkey per test cardholder, reused across tests."""
    if user_id not in _DEVICES:
        _DEVICES[user_id] = register(issuer, user_id)
    return _DEVICES[user_id]


def _assert_no_side_channel_headers(res) -> None:
    for name, value in res.headers.items():
        assert name.lower() in ALLOWED_HEADERS, f"unexpected header {name}: {value}"
        expected = ALLOWED_HEADERS[name.lower()]
        assert expected is None or value == expected, f"header {name} carries {value!r}"


# --- §2.5: exactly two keys, no side channel --------------------------------

def test_approved_purchase_reveals_exactly_two_keys(clients):
    merchant, issuer = clients
    order = _checkout(merchant)
    assert _verify(issuer, order["session_id"]).json() == {"result": "verified"}

    res = merchant.post("/checkout/complete", json={"instruction_id": order["instruction_id"]})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == APPROVAL_KEYS
    assert body["verified"] is True
    assert body["transaction_id"]
    _assert_no_side_channel_headers(res)


def test_unverified_purchase_reveals_exactly_two_keys(clients):
    merchant, _ = clients
    order = _checkout(merchant)
    res = merchant.post("/checkout/complete", json={"instruction_id": order["instruction_id"]})
    assert res.status_code == 200
    assert res.json() == {"verified": False, "transaction_id": None}
    _assert_no_side_channel_headers(res)


@pytest.mark.parametrize("verify_first", [True, False])
def test_issuer_approve_is_exactly_two_keys(clients, verify_first):
    merchant, issuer = clients
    order = _checkout(merchant)
    if verify_first:
        _verify(issuer, order["session_id"])
    res = issuer.post("/v1/approve", json={"instruction_id": order["instruction_id"]})
    assert res.status_code == 200
    assert set(res.json()) == APPROVAL_KEYS
    assert res.json()["verified"] is verify_first
    _assert_no_side_channel_headers(res)


# --- Identity never crosses to or from the merchant ------------------------

def test_merchant_sends_issuer_no_identity(clients, monkeypatch):
    merchant, issuer = clients
    sent = []
    real_post = issuer.post

    def spy(path, json=None, **kwargs):
        sent.append((path, set(json)))
        return real_post(path, json=json, **kwargs)

    monkeypatch.setattr(issuer, "post", spy)
    order = _checkout(merchant)
    merchant.post("/checkout/complete", json={"instruction_id": order["instruction_id"]})
    assert sent == [
        ("/v1/sessions", {"instruction_id", "amount_cents", "merchant_id"}),
        ("/v1/approve", {"instruction_id"}),
    ]


def test_issuer_rejects_identity_from_merchant(clients):
    _, issuer = clients
    res = issuer.post("/v1/sessions", json={
        "instruction_id": str(uuid.uuid4()), "amount_cents": 100, "merchant_id": "m", "user_id": USER_ID,
    })
    assert res.status_code == 422


def test_receipt_exposes_only_merchant_facts(clients):
    merchant, issuer = clients
    order = _checkout(merchant)
    _verify(issuer, order["session_id"])
    merchant.post("/checkout/complete", json={"instruction_id": order["instruction_id"]})
    receipt = merchant.get(f"/orders/{order['instruction_id']}").json()
    assert set(receipt) == {
        "instruction_id", "lines", "subtotal_cents", "tax_cents", "shipping_cents",
        "total_cents", "status", "transaction_id", "created_at",
    }
    assert receipt["status"] == "approved"
    assert receipt["total_cents"] == order["total_cents"]


def test_quote_prices_without_creating_anything(clients):
    merchant, _ = clients
    before = merchant_db.fetch_one("SELECT COUNT(*) AS n FROM orders")["n"]
    res = merchant.post("/cart/quote", json={"items": [{"product_id": PRODUCT_ID, "quantity": 3}]})
    assert res.status_code == 200
    assert res.json()["subtotal_cents"] == 3 * PRICE_CENTS
    assert "instruction_id" not in res.json()
    assert merchant_db.fetch_one("SELECT COUNT(*) AS n FROM orders")["n"] == before


def test_order_record_holds_no_verification_details(clients):
    columns = {r["name"] for r in merchant_db.fetch_all("PRAGMA table_info(orders)")}
    assert columns == {
        "instruction_id", "items_json", "subtotal_cents", "tax_cents", "shipping_cents",
        "total_cents", "status", "transaction_id", "created_at",
    }


# --- Pricing integrity -----------------------------------------------------

def test_issuer_charges_exactly_the_merchant_total(clients):
    merchant, issuer = clients
    order = _checkout(merchant, quantity=2)
    subtotal = 2 * PRICE_CENTS
    assert order["subtotal_cents"] == subtotal
    assert order["total_cents"] == subtotal + tax_for(subtotal) + shipping_for(subtotal)
    session = issuer.get(f"/v1/sessions/{order['session_id']}").json()
    assert session["amount_cents"] == order["total_cents"]


@pytest.mark.parametrize(("items", "status"), [
    ([{"product_id": PRODUCT_ID, "quantity": 1, "price_cents": 1}], 422),   # client-set price
    ([{"product_id": PRODUCT_ID, "quantity": 0}], 422),
    ([], 422),
    ([{"product_id": "no-such-product", "quantity": 1}], 400),
    ([{"product_id": PRODUCT_ID, "quantity": 1}, {"product_id": PRODUCT_ID, "quantity": 1}], 400),
])
def test_bad_carts_are_rejected(clients, items, status):
    merchant, _ = clients
    assert merchant.post("/checkout/confirm", json={"items": items}).status_code == status


def test_tax_rounds_half_up_in_integer_cents():
    assert tax_for(1237) == 49   # 49.48
    assert tax_for(1238) == 50   # 49.52


def test_shipping_threshold():
    assert shipping_for(FREE_SHIPPING_MIN_CENTS - 1) == SHIPPING_CENTS
    assert shipping_for(FREE_SHIPPING_MIN_CENTS) == 0


# --- Session state ---------------------------------------------------------

def test_session_cannot_be_verified_twice(clients):
    merchant, issuer = clients
    order = _checkout(merchant)
    assert _verify(issuer, order["session_id"]).status_code == 200
    assert _verify(issuer, order["session_id"]).status_code == 409


def test_unknown_cardholder_leaves_session_pending(clients):
    merchant, issuer = clients
    order = _checkout(merchant)
    assert _verify(issuer, order["session_id"], user_id="nobody").status_code == 404
    assert issuer.get(f"/v1/sessions/{order['session_id']}").json()["status"] == "pending"


def test_cardholder_list_requires_a_live_session(clients):
    merchant, issuer = clients
    assert issuer.get("/v1/cardholders").status_code == 404          # the old unscoped route is gone
    assert issuer.get("/v1/sessions/no-such-session/cardholders").status_code == 404
    order = _checkout(merchant)
    listed = issuer.get(f"/v1/sessions/{order['session_id']}/cardholders")
    assert listed.status_code == 200
    assert USER_ID in {c["id"] for c in listed.json()}
    _verify(issuer, order["session_id"])
    assert issuer.get(f"/v1/sessions/{order['session_id']}/cardholders").status_code == 409


class _ApprovingProvider(PaymentProvider):
    """Test double built on the interface: concrete providers are never
    imported outside issuer/payments/ (CLAUDE.md §6)."""
    def create_token(self, user_id, test_card):
        raise NotImplementedError

    def authorize(self, token, amount_cents, merchant_id, instruction_id):
        return AuthResult(ok=True, auth_id="test_auth", decline_reason=None)

    def capture(self, auth_id):
        return CaptureResult(ok=True, transaction_id="test_txn")

    def report_outcome(self, instruction_id, outcome):
        pass


class _DecliningProvider(_ApprovingProvider):
    def authorize(self, token, amount_cents, merchant_id, instruction_id):
        return AuthResult(ok=False, auth_id=None, decline_reason="test decline")


class _CaptureFailingProvider(_ApprovingProvider):
    def capture(self, auth_id):
        return CaptureResult(ok=False, transaction_id=None)


class _CrashingProvider(_ApprovingProvider):
    def authorize(self, token, amount_cents, merchant_id, instruction_id):
        raise RuntimeError("provider exploded")


@pytest.mark.parametrize("provider", [_DecliningProvider(), _CaptureFailingProvider()])
def test_payment_failure_never_dead_ends_the_session(clients, monkeypatch, provider):
    merchant, issuer = clients
    order = _checkout(merchant)
    with monkeypatch.context() as m:
        m.setattr(issuer_app.state, "provider", provider)
        assert _verify(issuer, order["session_id"]).json() == {"result": "payment_failed"}
    assert issuer.get(f"/v1/sessions/{order['session_id']}").json()["status"] == "pending"
    # The shopper can retry, and the retry succeeds once the payment does.
    assert _verify(issuer, order["session_id"]).json() == {"result": "verified"}


def test_provider_exception_releases_the_session(clients, monkeypatch):
    merchant, issuer = clients
    order = _checkout(merchant)
    with monkeypatch.context() as m:
        m.setattr(issuer_app.state, "provider", _CrashingProvider())
        with pytest.raises(RuntimeError, match="provider exploded"):
            _verify(issuer, order["session_id"])   # fails loudly, not silently
    assert issuer.get(f"/v1/sessions/{order['session_id']}").json()["status"] == "pending"
    assert _verify(issuer, order["session_id"]).json() == {"result": "verified"}


def test_session_can_be_extended_at_least_ten_times(clients):
    # WCAG 2.2.1 Timing Adjustable: the user can extend the limit at least ten times.
    merchant, issuer = clients
    order = _checkout(merchant)
    sid = order["session_id"]
    assert issuer.get(f"/v1/sessions/{sid}").json()["extensions_left"] == SESSION_MAX_EXTENSIONS
    for used in range(1, SESSION_MAX_EXTENSIONS + 1):
        res = issuer.post(f"/v1/sessions/{sid}/extend")
        assert res.status_code == 200
        assert res.json() == {"seconds_remaining": SESSION_TTL_SECONDS,
                              "extensions_left": SESSION_MAX_EXTENSIONS - used}
    assert issuer.post(f"/v1/sessions/{sid}/extend").status_code == 409
    assert _verify(issuer, sid).json() == {"result": "verified"}   # still usable after the cap


def test_expired_session_cannot_be_extended(clients):
    merchant, issuer = clients
    order = _checkout(merchant)
    with issuer_db.transaction() as conn:
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                     (order["session_id"],))
    assert issuer.post(f"/v1/sessions/{order['session_id']}/extend").status_code == 410


def test_expired_session_cannot_be_verified_or_approved(clients):
    merchant, issuer = clients
    order = _checkout(merchant)
    with issuer_db.transaction() as conn:
        conn.execute("UPDATE sessions SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                     (order["session_id"],))
    assert _verify(issuer, order["session_id"]).status_code == 410
    res = merchant.post("/checkout/complete", json={"instruction_id": order["instruction_id"]})
    assert res.json() == {"verified": False, "transaction_id": None}
