"""Feature 2: only authenticated market owners can create owned markets."""
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api import db as merchant_db
from api.db import fetch_one, transaction
from api.main import app


def _register(client: TestClient, email: str = "market@example.com") -> dict:
    response = client.post(
        "/market-auth/register",
        json={"email": email, "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return response.json()


def test_authenticated_owner_can_create_market():
    with TestClient(app) as client:
        owner = _register(client)
        response = client.post("/markets", json={"name": "  Aidan's   Market  "})

    assert response.status_code == 201
    market = response.json()
    assert market["name"] == "Aidan's Market"
    assert market["ownerAccountId"] == owner["id"]
    assert market["primaryColor"] == "#126B5B"
    assert market["logoUrl"] is None
    assert market["logoPlaceholder"] == "AM"
    row = fetch_one("SELECT * FROM markets WHERE id = ?", (market["id"],))
    assert row is not None
    assert row["owner_account_id"] == owner["id"]
    assert row["name"] == "Aidan's Market"


def test_unauthenticated_market_creation_is_rejected_without_writing():
    with TestClient(app) as client:
        response = client.post("/markets", json={"name": "Orphan Market"})
    assert response.status_code == 401
    assert fetch_one("SELECT 1 FROM markets WHERE name = ?", ("Orphan Market",)) is None


def test_client_cannot_choose_or_spoof_market_owner():
    with TestClient(app) as client:
        owner = _register(client, "real-owner@example.com")
        other = client.post(
            "/market-auth/register",
            json={"email": "other-owner@example.com", "password": "correct horse battery"},
        ).json()
        response = client.post(
            "/markets",
            json={"name": "Spoofed Market", "ownerAccountId": owner["id"]},
        )
    assert owner["id"] != other["id"]
    assert response.status_code == 422
    assert fetch_one("SELECT 1 FROM markets WHERE name = ?", ("Spoofed Market",)) is None


@pytest.mark.parametrize("name", ["", "   ", "\n\t"])
def test_market_name_is_required(name):
    with TestClient(app) as client:
        _register(client, f"blank-{uuid.uuid4()}@example.com")
        response = client.post("/markets", json={"name": name})
    assert response.status_code == 422


def test_database_rejects_non_owner_and_missing_accounts():
    buyer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        conn.execute(
            "INSERT INTO accounts (id, email, password_hash, role, created_at)"
            " VALUES (?, ?, 'unused', 'BUYER', ?)",
            (buyer_id, f"{buyer_id}@example.com", now),
        )

    with pytest.raises(sqlite3.IntegrityError, match="market owner account required"):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO markets (id, name, owner_account_id, created_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "Buyer Market", buyer_id, now),
            )

    with pytest.raises(sqlite3.IntegrityError, match="market owner account required"):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO markets (id, name, owner_account_id, created_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "Orphan Market", str(uuid.uuid4()), now),
            )


def test_market_owner_can_update_and_public_can_read_branding():
    with TestClient(app) as client:
        owner = _register(client, "branding@example.com")
        created = client.post("/markets", json={"name": "Old Name"}).json()
        updated = client.patch(
            f"/markets/{created['id']}/branding",
            json={
                "name": "  Harbor   Foods ",
                "primaryColor": "#a1b2c3",
                "logoUrl": "https://cdn.example.com/harbor-logo.png",
            },
        )
        client.cookies.clear()
        public = client.get(f"/markets/{created['id']}")

    assert updated.status_code == 200
    assert updated.json()["name"] == "Harbor Foods"
    assert updated.json()["primaryColor"] == "#A1B2C3"
    assert updated.json()["logoUrl"] == "https://cdn.example.com/harbor-logo.png"
    assert updated.json()["logoPlaceholder"] == "HF"
    assert public.status_code == 200
    assert public.json() == {key: value for key, value in updated.json().items() if key != "ownerAccountId"}
    assert "ownerAccountId" not in public.json()


def test_owner_can_use_static_logo_and_clear_it_to_placeholder():
    with TestClient(app) as client:
        _register(client, "static-logo@example.com")
        market = client.post("/markets", json={"name": "Corner Shop"}).json()
        local = client.patch(
            f"/markets/{market['id']}/branding", json={"logoUrl": "/market-logos/corner.svg"}
        )
        cleared = client.patch(f"/markets/{market['id']}/branding", json={"logoUrl": None})
    assert local.status_code == 200
    assert local.json()["logoUrl"] == "/market-logos/corner.svg"
    assert cleared.status_code == 200
    assert cleared.json()["logoUrl"] is None
    assert cleared.json()["logoPlaceholder"] == "CS"


def test_market_owner_cannot_brand_another_owners_market():
    with TestClient(app) as client:
        _register(client, "first-brand-owner@example.com")
        market = client.post("/markets", json={"name": "First Market"}).json()
        client.cookies.clear()
        _register(client, "second-brand-owner@example.com")
        denied = client.patch(
            f"/markets/{market['id']}/branding", json={"primaryColor": "#ABCDEF"}
        )
    assert denied.status_code == 404
    row = fetch_one("SELECT primary_color FROM markets WHERE id = ?", (market["id"],))
    assert row["primary_color"] == "#126B5B"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"name": "   "},
        {"primaryColor": "blue"},
        {"primaryColor": "#12345"},
        {"logoUrl": "javascript:alert(1)"},
        {"logoUrl": "http://insecure.example/logo.png"},
        {"logoUrl": "//evil.example/logo.png"},
    ],
)
def test_invalid_branding_is_rejected_without_mutation(body):
    with TestClient(app) as client:
        _register(client, f"brand-validation-{uuid.uuid4()}@example.com")
        market = client.post("/markets", json={"name": "Safe Market"}).json()
        response = client.patch(f"/markets/{market['id']}/branding", json=body)
    assert response.status_code == 422
    row = fetch_one("SELECT name, primary_color, logo_url FROM markets WHERE id = ?", (market["id"],))
    assert dict(row) == {"name": "Safe Market", "primary_color": "#126B5B", "logo_url": None}


def test_unknown_market_branding_returns_not_found():
    unknown = str(uuid.uuid4())
    with TestClient(app) as client:
        _register(client, "unknown-market@example.com")
        assert client.get(f"/markets/{unknown}").status_code == 404
        assert client.patch(
            f"/markets/{unknown}/branding", json={"primaryColor": "#ABCDEF"}
        ).status_code == 404


def test_branding_columns_migrate_feature_two_database(tmp_path, monkeypatch):
    old_db = tmp_path / "feature-two.db"
    conn = sqlite3.connect(old_db)
    conn.executescript(
        """
        CREATE TABLE accounts (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE markets (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_account_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO accounts VALUES ('owner', 'owner@example.com', 'unused', 'MARKET_OWNER', 'now');
        INSERT INTO markets VALUES ('market', 'Existing Market', 'owner', 'now');
        """
    )
    conn.close()
    monkeypatch.setattr(merchant_db, "MERCHANT_DB", old_db)

    merchant_db.init_db()

    row = merchant_db.fetch_one(
        "SELECT primary_color, logo_url FROM markets WHERE id = 'market'"
    )
    assert dict(row) == {"primary_color": "#126B5B", "logo_url": None}


def _pickup_address(**overrides) -> dict:
    return {
        "addressLine1": "  10  Harbor Road ",
        "addressLine2": " Unit 3 ",
        "city": "  Boston ",
        "stateRegion": " MA ",
        "postalCode": " 02110 ",
        "country": " United States ",
        **overrides,
    }


def test_owner_can_set_address_and_enable_pickup_in_one_request():
    with TestClient(app) as client:
        _register(client, "pickup-owner@example.com")
        market = client.post("/markets", json={"name": "Pickup Market"}).json()
        updated = client.patch(
            f"/markets/{market['id']}/pickup-settings",
            json={"pickupEnabled": True, "pickupAddress": _pickup_address()},
        )
        fetched = client.get(f"/markets/{market['id']}/pickup-settings")
    assert updated.status_code == 200
    assert updated.json() == {
        "pickupEnabled": True,
        "pickupAddress": {
            "addressLine1": "10 Harbor Road",
            "addressLine2": "Unit 3",
            "city": "Boston",
            "stateRegion": "MA",
            "postalCode": "02110",
            "country": "United States",
        },
    }
    assert fetched.json() == updated.json()
    row = fetch_one("SELECT pickup_enabled FROM markets WHERE id = ?", (market["id"],))
    assert row["pickup_enabled"] == 1


def test_owner_can_save_address_while_disabled_then_enable_and_disable_pickup():
    with TestClient(app) as client:
        _register(client, "pickup-toggle@example.com")
        market = client.post("/markets", json={"name": "Toggle Market"}).json()
        saved = client.patch(
            f"/markets/{market['id']}/pickup-settings", json={"pickupAddress": _pickup_address()}
        )
        enabled = client.patch(
            f"/markets/{market['id']}/pickup-settings", json={"pickupEnabled": True}
        )
        disabled = client.patch(
            f"/markets/{market['id']}/pickup-settings", json={"pickupEnabled": False}
        )
        removed = client.patch(
            f"/markets/{market['id']}/pickup-settings",
            json={"pickupAddress": None},
        )
    assert saved.status_code == 200
    assert saved.json()["pickupEnabled"] is False
    assert enabled.json()["pickupEnabled"] is True
    assert disabled.json()["pickupEnabled"] is False
    assert removed.status_code == 200
    assert removed.json() == {"pickupEnabled": False, "pickupAddress": None}


def test_pickup_cannot_be_enabled_or_address_removed_without_valid_configuration():
    with TestClient(app) as client:
        _register(client, "pickup-validation@example.com")
        market = client.post("/markets", json={"name": "Validation Market"}).json()
        no_address = client.patch(
            f"/markets/{market['id']}/pickup-settings", json={"pickupEnabled": True}
        )
        invalid_address = client.patch(
            f"/markets/{market['id']}/pickup-settings",
            json={"pickupEnabled": True, "pickupAddress": _pickup_address(city=" ")},
        )
        client.patch(
            f"/markets/{market['id']}/pickup-settings",
            json={"pickupEnabled": True, "pickupAddress": _pickup_address()},
        )
        remove_enabled = client.patch(
            f"/markets/{market['id']}/pickup-settings", json={"pickupAddress": None}
        )
    assert no_address.status_code == 422
    assert invalid_address.status_code == 422
    assert remove_enabled.status_code == 422
    row = fetch_one("SELECT pickup_enabled FROM markets WHERE id = ?", (market["id"],))
    assert row["pickup_enabled"] == 1
    assert fetch_one("SELECT 1 FROM market_pickup_addresses WHERE market_id = ?", (market["id"],))


def test_other_owners_and_anonymous_callers_cannot_manage_pickup():
    with TestClient(app) as client:
        _register(client, "pickup-first@example.com")
        market = client.post("/markets", json={"name": "Private Pickup"}).json()
        client.cookies.clear()
        anonymous = client.get(f"/markets/{market['id']}/pickup-settings")
        _register(client, "pickup-second@example.com")
        other = client.patch(
            f"/markets/{market['id']}/pickup-settings",
            json={"pickupAddress": _pickup_address()},
        )
    assert anonymous.status_code == 401
    assert other.status_code == 404
    assert fetch_one("SELECT 1 FROM market_pickup_addresses WHERE market_id = ?", (market["id"],)) is None


def test_database_enforces_pickup_address_invariant():
    with TestClient(app) as client:
        owner = _register(client, "pickup-db-owner@example.com")
        market = client.post("/markets", json={"name": "Database Pickup"}).json()
    with pytest.raises(sqlite3.IntegrityError, match="pickup address required"):
        with transaction() as conn:
            conn.execute("UPDATE markets SET pickup_enabled = 1 WHERE id = ?", (market["id"],))
    with transaction() as conn:
        conn.execute(
            "INSERT INTO market_pickup_addresses "
            "(market_id, address_line_1, city, state_region, postal_code, country, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (market["id"], "10 Harbor", "Boston", "MA", "02110", "US", "now"),
        )
        conn.execute("UPDATE markets SET pickup_enabled = 1 WHERE id = ?", (market["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="disable pickup"):
        with transaction() as conn:
            conn.execute("DELETE FROM market_pickup_addresses WHERE market_id = ?", (market["id"],))


def test_owner_can_set_shipping_methods_and_enable_shipping():
    with TestClient(app) as client:
        _register(client, "shipping-owner@example.com")
        market = client.post("/markets", json={"name": "Shipping Market"}).json()
        updated = client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"shippingEnabled": True, "supportedShippingMethods": ["UPS", "USPS", "LOCAL_DRIVER"]},
        )
        fetched = client.get(f"/markets/{market['id']}/shipping-settings")
    assert updated.status_code == 200
    assert updated.json() == {
        "shippingEnabled": True,
        "supportedShippingMethods": ["LOCAL_DRIVER", "UPS", "USPS"],
    }
    assert fetched.json() == updated.json()
    row = fetch_one("SELECT shipping_enabled FROM markets WHERE id = ?", (market["id"],))
    assert row["shipping_enabled"] == 1


def test_owner_can_save_methods_disabled_then_enable_and_replace_them():
    with TestClient(app) as client:
        _register(client, "shipping-toggle@example.com")
        market = client.post("/markets", json={"name": "Shipping Toggle"}).json()
        saved = client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"supportedShippingMethods": ["FEDEX"]},
        )
        enabled = client.patch(
            f"/markets/{market['id']}/shipping-settings", json={"shippingEnabled": True}
        )
        replaced = client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"supportedShippingMethods": ["USPS", "LOCAL_DRIVER"]},
        )
        disabled = client.patch(
            f"/markets/{market['id']}/shipping-settings", json={"shippingEnabled": False}
        )
        cleared = client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"supportedShippingMethods": []},
        )
    assert saved.json() == {"shippingEnabled": False, "supportedShippingMethods": ["FEDEX"]}
    assert enabled.json() == {"shippingEnabled": True, "supportedShippingMethods": ["FEDEX"]}
    assert replaced.json() == {
        "shippingEnabled": True,
        "supportedShippingMethods": ["LOCAL_DRIVER", "USPS"],
    }
    assert disabled.json()["shippingEnabled"] is False
    assert cleared.json() == {"shippingEnabled": False, "supportedShippingMethods": []}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"shippingEnabled": True},
        {"shippingEnabled": True, "supportedShippingMethods": []},
        {"supportedShippingMethods": ["UPS", "UPS"]},
        {"supportedShippingMethods": ["DHL"]},
        {"shippingEnabled": "yes", "supportedShippingMethods": ["UPS"]},
    ],
)
def test_invalid_shipping_configuration_does_not_mutate_market(body):
    with TestClient(app) as client:
        _register(client, f"shipping-invalid-{uuid.uuid4()}@example.com")
        market = client.post("/markets", json={"name": "Safe Shipping"}).json()
        response = client.patch(f"/markets/{market['id']}/shipping-settings", json=body)
    assert response.status_code == 422
    row = fetch_one("SELECT shipping_enabled FROM markets WHERE id = ?", (market["id"],))
    assert row["shipping_enabled"] == 0
    assert fetch_one("SELECT 1 FROM market_shipping_methods WHERE market_id = ?", (market["id"],)) is None


def test_other_owners_and_anonymous_callers_cannot_manage_shipping():
    with TestClient(app) as client:
        _register(client, "shipping-first@example.com")
        market = client.post("/markets", json={"name": "Private Shipping"}).json()
        client.cookies.clear()
        anonymous = client.get(f"/markets/{market['id']}/shipping-settings")
        _register(client, "shipping-second@example.com")
        other = client.patch(
            f"/markets/{market['id']}/shipping-settings",
            json={"supportedShippingMethods": ["UPS"]},
        )
    assert anonymous.status_code == 401
    assert other.status_code == 404
    assert fetch_one("SELECT 1 FROM market_shipping_methods WHERE market_id = ?", (market["id"],)) is None


def test_database_enforces_shipping_method_invariant():
    with TestClient(app) as client:
        _register(client, "shipping-db-owner@example.com")
        market = client.post("/markets", json={"name": "Database Shipping"}).json()
    with pytest.raises(sqlite3.IntegrityError, match="shipping method required"):
        with transaction() as conn:
            conn.execute("UPDATE markets SET shipping_enabled = 1 WHERE id = ?", (market["id"],))
    with transaction() as conn:
        conn.execute(
            "INSERT INTO market_shipping_methods (market_id, method) VALUES (?, ?)",
            (market["id"], "UPS"),
        )
        conn.execute("UPDATE markets SET shipping_enabled = 1 WHERE id = ?", (market["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="disable shipping"):
        with transaction() as conn:
            conn.execute("DELETE FROM market_shipping_methods WHERE market_id = ?", (market["id"],))
