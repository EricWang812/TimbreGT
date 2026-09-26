"""Feature 13: buyer fulfillment selection uses live market configuration."""
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from api.db import fetch_one, transaction
from api.main import app


def _owner(client: TestClient) -> dict:
    response = client.post(
        "/market-auth/register",
        json={"email": f"fulfillment-owner-{uuid.uuid4()}@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return response.json()


def _buyer(client: TestClient) -> dict:
    response = client.post(
        "/buyer-auth/register",
        json={"email": f"fulfillment-buyer-{uuid.uuid4()}@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return response.json()


def _pickup_address() -> dict:
    return {
        "addressLine1": "10 Harbor Road",
        "city": "Boston",
        "stateRegion": "MA",
        "postalCode": "02110",
        "country": "United States",
    }


def _shipping_address() -> dict:
    return {
        "recipientName": "Ada Lovelace",
        "addressLine1": "12 Main Street",
        "city": "Boston",
        "stateRegion": "MA",
        "postalCode": "02110",
        "country": "United States",
    }


def _market(client: TestClient, name: str = "Fulfillment Market") -> dict:
    response = client.post("/markets", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_options_show_only_configured_shipping_and_pickup_methods():
    with TestClient(app) as client:
        _owner(client)
        market = _market(client)
        client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"shippingEnabled": True, "supportedShippingMethods": ["UPS"]},
        )
        client.patch(
            f"/markets/{market['id']}/pickup-settings",
            json={"pickupEnabled": True, "pickupAddress": _pickup_address()},
        )
        client.cookies.clear()
        _buyer(client)
        options = client.get(f"/buyer/markets/{market['id']}/fulfillment-options")
    assert options.status_code == 200
    assert options.json() == {
        "marketId": market["id"],
        "availableMethods": ["SHIP", "PICKUP"],
        "supportedShippingMethods": ["UPS"],
        "pickupAddress": {**_pickup_address(), "addressLine2": None},
    }


def test_shipping_requires_the_current_buyers_saved_address():
    with TestClient(app) as client:
        _owner(client)
        market = _market(client, "Shipping Only")
        client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"shippingEnabled": True, "supportedShippingMethods": ["USPS"]},
        )
        client.cookies.clear()
        buyer = _buyer(client)
        missing = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "SHIP"},
        )
        unknown = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "SHIP", "shippingAddressId": str(uuid.uuid4())},
        )
        address = client.post("/buyer/addresses", json=_shipping_address()).json()
        selected = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "SHIP", "shippingAddressId": address["id"]},
        )
    assert missing.status_code == 422
    assert unknown.status_code == 422
    assert selected.status_code == 200
    assert selected.json() == {
        "marketId": market["id"],
        "fulfillmentMethod": "SHIP",
        "shippingAddressId": address["id"],
        "pickupAddress": None,
    }
    row = fetch_one(
        "SELECT buyer_account_id, fulfillment_method, shipping_address_id "
        "FROM buyer_market_fulfillment_selections WHERE market_id = ?", (market["id"],)
    )
    assert dict(row) == {
        "buyer_account_id": buyer["id"],
        "fulfillment_method": "SHIP",
        "shipping_address_id": address["id"],
    }


def test_pickup_returns_pickup_address_and_does_not_accept_shipping_address():
    with TestClient(app) as client:
        _owner(client)
        market = _market(client, "Pickup Only")
        client.patch(
            f"/markets/{market['id']}/pickup-settings",
            json={"pickupEnabled": True, "pickupAddress": _pickup_address()},
        )
        client.cookies.clear()
        _buyer(client)
        selected = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "PICKUP"},
        )
        invalid = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "PICKUP", "shippingAddressId": str(uuid.uuid4())},
        )
    assert selected.status_code == 200
    assert selected.json()["shippingAddressId"] is None
    assert selected.json()["pickupAddress"] == {**_pickup_address(), "addressLine2": None}
    assert invalid.status_code == 422


def test_selection_rejects_disabled_methods_and_other_buyer_address():
    with TestClient(app) as client:
        _owner(client)
        market = _market(client, "Unavailable")
        client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"shippingEnabled": True, "supportedShippingMethods": ["UPS"]},
        )
        client.cookies.clear()
        _buyer(client)
        other_address = client.post("/buyer/addresses", json=_shipping_address()).json()
        client.cookies.clear()
        second_buyer = _buyer(client)
        unavailable = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "PICKUP"},
        )
        cross_buyer_address = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "SHIP", "shippingAddressId": other_address["id"]},
        )
    assert unavailable.status_code == 409
    assert cross_buyer_address.status_code == 422
    assert fetch_one(
        "SELECT 1 FROM buyer_market_fulfillment_selections "
        "WHERE buyer_account_id = ? AND market_id = ?",
        (second_buyer["id"], market["id"]),
    ) is None


def test_anonymous_fulfillment_calls_are_rejected():
    with TestClient(app) as client:
        _owner(client)
        market = _market(client, "Private Options")
        client.cookies.clear()
        options = client.get(f"/buyer/markets/{market['id']}/fulfillment-options")
        selection = client.put(
            f"/buyer/markets/{market['id']}/fulfillment-selection",
            json={"fulfillmentMethod": "PICKUP"},
        )
    assert options.status_code == 401
    assert selection.status_code == 401


def test_database_rejects_selection_address_owned_by_another_buyer():
    with TestClient(app) as client:
        _owner(client)
        market = _market(client, "Selection Database")
        client.cookies.clear()
        first = _buyer(client)
        address = client.post("/buyer/addresses", json=_shipping_address()).json()
        client.cookies.clear()
        second = _buyer(client)
    with pytest.raises(sqlite3.IntegrityError, match="shipping address must belong to buyer"):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO buyer_market_fulfillment_selections "
                "(buyer_account_id, market_id, fulfillment_method, shipping_address_id, created_at, updated_at) "
                "VALUES (?, ?, 'SHIP', ?, 'now', 'now')",
                (second["id"], market["id"], address["id"]),
            )
    assert first["id"] != second["id"]
