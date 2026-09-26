"""Feature 14: market orders are created only after issuer approval."""
import json
import uuid

from fastapi.testclient import TestClient

from api import issuer_client
from api.db import fetch_all, fetch_one
from api.main import app


def _owner(client: TestClient) -> None:
    response = client.post(
        "/market-auth/register",
        json={"email": f"order-owner-{uuid.uuid4()}@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201


def _buyer(client: TestClient) -> dict:
    response = client.post(
        "/buyer-auth/register",
        json={"email": f"order-buyer-{uuid.uuid4()}@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return response.json()


def _market_product(client: TestClient) -> tuple[dict, dict]:
    _owner(client)
    market = client.post("/markets", json={"name": "Order Market"}).json()
    product = client.post(
        f"/markets/{market['id']}/products",
        json={"name": "Fuji Apples", "price": 3.99, "quantity": 2, "unit": "lb"},
    ).json()
    return market, product


def _shipping_selection(client: TestClient, market_id: str) -> None:
    client.patch(
        f"/markets/{market_id}/shipping-settings",
        json={"shippingEnabled": True, "supportedShippingMethods": ["UPS"]},
    )
    client.cookies.clear()
    _buyer(client)
    address = client.post(
        "/buyer/addresses",
        json={
            "recipientName": "Ada Lovelace", "addressLine1": "12 Main Street", "city": "Boston",
            "stateRegion": "MA", "postalCode": "02110", "country": "United States",
        },
    ).json()
    selected = client.put(
        f"/buyer/markets/{market_id}/fulfillment-selection",
        json={"fulfillmentMethod": "SHIP", "shippingAddressId": address["id"]},
    )
    assert selected.status_code == 200


def test_market_order_is_snapshotted_only_after_verified_existing_checkout(monkeypatch):
    monkeypatch.setattr(issuer_client, "create_session", lambda instruction_id, amount, merchant_id: "issuer-session")
    monkeypatch.setattr(
        issuer_client, "approve", lambda instruction_id: {"verified": True, "transaction_id": "txn-market"}
    )
    with TestClient(app) as client:
        market, product = _market_product(client)
        _shipping_selection(client, market["id"])
        confirmed = client.post(
            f"/buyer/markets/{market['id']}/checkout/confirm",
            json={"items": [{"productId": product["id"], "quantity": 2}]},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["subtotalCents"] == 798
        assert fetch_one("SELECT 1 FROM market_orders WHERE instruction_id = ?", (confirmed.json()["instructionId"],)) is None
        client.cookies.clear()
        completed = client.post("/checkout/complete", json={"instruction_id": confirmed.json()["instructionId"]})
    assert completed.json() == {"verified": True, "transaction_id": "txn-market"}
    order = fetch_one("SELECT * FROM market_orders WHERE instruction_id = ?", (confirmed.json()["instructionId"],))
    assert order["buyer_account_id"]
    assert order["market_id"] == market["id"]
    assert order["subtotal_cents"] == 798
    assert order["total_cents"] == 798
    assert order["fulfillment_method"] == "SHIP"
    assert order["status"] == "NOT_STARTED"
    assert json.loads(order["shipping_address_json"])["recipientName"] == "Ada Lovelace"
    items = fetch_all("SELECT * FROM market_order_items WHERE order_id = ?", (order["id"],))
    assert len(items) == 1
    item = dict(items[0])
    assert item["product_id"] == product["id"]
    assert item["product_name"] == "Fuji Apples"
    assert item["price_cents"] == 399
    assert item["amount"] == 2
    assert item["quantity_value"] == 2.0
    assert item["quantity_unit"] == "lb"


def test_market_checkout_requires_buyer_selection_and_does_not_accept_other_market_products(monkeypatch):
    monkeypatch.setattr(issuer_client, "create_session", lambda *args: "issuer-session")
    with TestClient(app) as client:
        market, product = _market_product(client)
        client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"shippingEnabled": True, "supportedShippingMethods": ["UPS"]},
        )
        client.cookies.clear()
        _buyer(client)
        no_selection = client.post(
            f"/buyer/markets/{market['id']}/checkout/confirm",
            json={"items": [{"productId": product["id"], "quantity": 1}]},
        )
        client.cookies.clear()
        _owner(client)
        other_market = client.post("/markets", json={"name": "Other Order Market"}).json()
        other_product = client.post(
            f"/markets/{other_market['id']}/products", json={"name": "Milk", "price": 2.50},
        ).json()
        client.cookies.clear()
        _buyer(client)
        address = client.post(
            "/buyer/addresses",
            json={
                "recipientName": "Ada Lovelace", "addressLine1": "12 Main Street", "city": "Boston",
                "stateRegion": "MA", "postalCode": "02110", "country": "United States",
            },
        ).json()
        assert client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "SHIP", "shippingAddressId": address["id"]},
        ).status_code == 200
        wrong_product = client.post(
            f"/buyer/markets/{market['id']}/checkout/confirm",
            json={"items": [{"productId": other_product["id"], "quantity": 1}]},
        )
    assert no_selection.status_code == 422
    assert wrong_product.status_code == 422
    assert fetch_one("SELECT 1 FROM market_checkout_sessions WHERE market_id = ?", (market["id"],)) is None


def test_unverified_market_checkout_never_creates_an_order(monkeypatch):
    monkeypatch.setattr(issuer_client, "create_session", lambda *args: "issuer-session")
    monkeypatch.setattr(
        issuer_client, "approve", lambda instruction_id: {"verified": False, "transaction_id": None}
    )
    with TestClient(app) as client:
        market, product = _market_product(client)
        _shipping_selection(client, market["id"])
        confirmed = client.post(
            f"/buyer/markets/{market['id']}/checkout/confirm",
            json={"items": [{"productId": product["id"], "quantity": 1}]},
        ).json()
        result = client.post("/checkout/complete", json={"instruction_id": confirmed["instructionId"]})
    assert result.json() == {"verified": False, "transaction_id": None}
    assert fetch_one("SELECT 1 FROM market_orders WHERE instruction_id = ?", (confirmed["instructionId"],)) is None


def test_multi_market_checkout_creates_one_private_order_per_market(monkeypatch):
    monkeypatch.setattr(issuer_client, "create_session", lambda *args: "issuer-session")
    monkeypatch.setattr(issuer_client, "approve", lambda instruction_id: {"verified": True, "transaction_id": "txn-split"})
    with TestClient(app) as client:
        first_market, first_product = _market_product(client)
        client.patch(f"/markets/{first_market['id']}/shipping-settings", json={"shippingEnabled": True, "supportedShippingMethods": ["UPS"]})
        client.cookies.clear()
        _owner(client)
        second_market = client.post("/markets", json={"name": "Second Order Market"}).json()
        second_product = client.post(f"/markets/{second_market['id']}/products", json={"name": "Milk", "price": 2.50}).json()
        client.patch(f"/markets/{second_market['id']}/shipping-settings", json={"shippingEnabled": True, "supportedShippingMethods": ["USPS"]})
        client.cookies.clear()
        _buyer(client)
        address = client.post("/buyer/addresses", json={"recipientName": "Ada", "addressLine1": "1 Main", "city": "Boston", "stateRegion": "MA", "postalCode": "02110", "country": "US"}).json()
        for market in (first_market, second_market):
            assert client.put(f"/buyer/markets/{market['id']}/fulfillment-selection", json={"fulfillmentMethod": "SHIP", "shippingAddressId": address["id"]}).status_code == 200
        confirmed = client.post("/buyer/markets/checkout/confirm", json={"items": [
            {"marketId": first_market["id"], "productId": first_product["id"], "quantity": 1},
            {"marketId": second_market["id"], "productId": second_product["id"], "quantity": 2},
        ]})
        assert confirmed.status_code == 200
        assert confirmed.json()["totalCents"] == 899
        assert client.post("/checkout/complete", json={"instruction_id": confirmed.json()["instructionId"]}).json() == {"verified": True, "transaction_id": "txn-split"}
    rows = fetch_all("SELECT market_id, subtotal_cents, transaction_id FROM market_orders WHERE transaction_id = ? ORDER BY market_id", ("txn-split",))
    assert [(row["market_id"], row["subtotal_cents"], row["transaction_id"]) for row in rows] == sorted([
        (first_market["id"], 399, "txn-split"), (second_market["id"], 500, "txn-split"),
    ])
