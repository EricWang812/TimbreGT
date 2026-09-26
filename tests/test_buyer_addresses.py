"""Feature 10: buyers can keep private shipping addresses."""
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from api.db import fetch_one, transaction
from api.main import app


def _register(client: TestClient, email: str | None = None) -> dict:
    response = client.post(
        "/buyer-auth/register",
        json={
            "email": email or f"address-buyer-{uuid.uuid4()}@example.com",
            "password": "correct horse battery",
        },
    )
    assert response.status_code == 201
    return response.json()


def _address(**overrides) -> dict:
    return {
        "recipientName": "  Ada   Lovelace ",
        "addressLine1": "  12  Main Street ",
        "addressLine2": " Apt. 4 ",
        "city": "  Boston ",
        "stateRegion": " MA ",
        "postalCode": " 02110 ",
        "country": " United States ",
        **overrides,
    }


def test_buyer_can_create_and_list_their_shipping_addresses():
    with TestClient(app) as client:
        buyer = _register(client)
        created = client.post("/buyer/addresses", json=_address())
        listed = client.get("/buyer/addresses")
    assert created.status_code == 201
    address = created.json()
    assert address | {"id": "ignored", "createdAt": "ignored"} == {
        "id": "ignored",
        "recipientName": "Ada Lovelace",
        "addressLine1": "12 Main Street",
        "addressLine2": "Apt. 4",
        "city": "Boston",
        "stateRegion": "MA",
        "postalCode": "02110",
        "country": "United States",
        "createdAt": "ignored",
    }
    assert listed.status_code == 200
    assert listed.json() == [address]
    row = fetch_one("SELECT * FROM buyer_addresses WHERE id = ?", (address["id"],))
    assert row is not None
    assert row["buyer_account_id"] == buyer["id"]
    assert row["postal_code"] == "02110"


def test_optional_address_line_two_can_be_omitted_or_blank():
    with TestClient(app) as client:
        _register(client)
        omitted = client.post("/buyer/addresses", json=_address(addressLine2=None))
        blank = client.post("/buyer/addresses", json=_address(addressLine2="   "))
    assert omitted.status_code == 201
    assert omitted.json()["addressLine2"] is None
    assert blank.status_code == 201
    assert blank.json()["addressLine2"] is None


def test_buyer_cannot_read_another_buyers_addresses():
    with TestClient(app) as client:
        _register(client)
        created = client.post("/buyer/addresses", json=_address()).json()
        client.cookies.clear()
        _register(client)
        other_addresses = client.get("/buyer/addresses")
    assert other_addresses.status_code == 200
    assert other_addresses.json() == []
    assert fetch_one("SELECT 1 FROM buyer_addresses WHERE id = ?", (created["id"],)) is not None


def test_anonymous_address_access_is_rejected():
    with TestClient(app) as client:
        created = client.post("/buyer/addresses", json=_address())
        listed = client.get("/buyer/addresses")
    assert created.status_code == 401
    assert listed.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"recipientName": "Ada"},
        _address(recipientName="  "),
        _address(addressLine1="  "),
        _address(city="  "),
        _address(stateRegion="  "),
        _address(postalCode="  "),
        _address(country="  "),
        _address(buyerAccountId=str(uuid.uuid4())),
    ],
)
def test_invalid_address_is_rejected_without_writing(body):
    with TestClient(app) as client:
        buyer = _register(client)
        response = client.post("/buyer/addresses", json=body)
    assert response.status_code == 422
    assert fetch_one("SELECT 1 FROM buyer_addresses WHERE buyer_account_id = ?", (buyer["id"],)) is None


def test_database_rejects_addresses_for_nonbuyers():
    with TestClient(app) as client:
        owner = client.post(
            "/market-auth/register",
            json={"email": f"owner-{uuid.uuid4()}@example.com", "password": "correct horse battery"},
        ).json()
    with pytest.raises(sqlite3.IntegrityError):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO buyer_addresses "
                "(id, buyer_account_id, recipient_name, address_line_1, city, state_region, "
                "postal_code, country, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), owner["id"], "Ada", "12 Main", "Boston", "MA", "02110", "US", "now"),
            )
