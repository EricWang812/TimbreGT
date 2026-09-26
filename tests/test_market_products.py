"""Authenticated owners can create and manage market products."""
import sqlite3
import uuid

import pytest
from fastapi.testclient import TestClient

from api.db import fetch_one, init_db, transaction
from api.main import app
from api.market_units import normalize_quantity, units_are_compatible


def _register(client: TestClient) -> dict:
    response = client.post(
        "/market-auth/register",
        json={
            "email": f"product-owner-{uuid.uuid4()}@example.com",
            "password": "correct horse battery",
        },
    )
    assert response.status_code == 201
    return response.json()


def _market(client: TestClient, name: str = "Product Market") -> dict:
    response = client.post("/markets", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_owner_can_create_product_for_owned_market():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(
            f"/markets/{market['id']}/products",
            json={
                "name": "  Fuji   Apples ",
                "price": 3.99,
                "photoUrl": "https://cdn.example.com/fuji-apples.jpg",
            },
        )

    assert response.status_code == 201
    product = response.json()
    assert product["marketId"] == market["id"]
    assert product["name"] == "Fuji Apples"
    assert product["price"] == 3.99
    assert product["priceCents"] == 399
    assert product["photoUrl"] == "https://cdn.example.com/fuji-apples.jpg"
    assert product["quantity"] is None
    assert product["unit"] is None
    row = fetch_one("SELECT * FROM market_products WHERE id = ?", (product["id"],))
    assert row is not None
    assert row["market_id"] == market["id"]
    assert row["price_cents"] == 399


def test_product_photo_is_optional_and_zero_price_is_valid():
    with TestClient(app) as client:
        _register(client)
        market = _market(client, "Free Samples")
        response = client.post(
            f"/markets/{market['id']}/products", json={"name": "Sample", "price": 0}
        )
    assert response.status_code == 201
    assert response.json()["priceCents"] == 0
    assert response.json()["photoUrl"] is None
    assert response.json()["quantityPerDollar"] is None


@pytest.mark.parametrize(
    ("quantity", "unit", "price", "expected"),
    [(2, "lb", 4, 0.5), (750, "mL", 3, 250), (12, "count", 6, 2)],
)
def test_quantity_per_dollar_is_calculated_from_measurement_and_price(
    quantity, unit, price, expected
):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(
            f"/markets/{market['id']}/products",
            json={"name": "Measured", "price": price, "quantity": quantity, "unit": unit},
        )
    assert response.status_code == 201
    product = response.json()
    assert product["quantityPerDollar"] == expected
    assert product["unit"] == unit


def test_quantity_per_dollar_updates_without_being_stored():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = client.post(
            f"/markets/{market['id']}/products",
            json={"name": "Apples", "price": 4, "quantity": 2, "unit": "lb"},
        ).json()
        updated = client.patch(
            f"/markets/{market['id']}/products/{product['id']}", json={"price": 2}
        )
        listed = client.get(f"/markets/{market['id']}/products")
    assert updated.status_code == 200
    assert updated.json()["quantityPerDollar"] == 1
    assert listed.status_code == 200
    assert listed.json()[0]["quantityPerDollar"] == 1
    row = fetch_one("SELECT * FROM market_products WHERE id = ?", (product["id"],))
    assert "quantity_per_dollar" not in row.keys()


def test_quantity_per_dollar_is_unavailable_for_unmeasured_products():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"])
    assert product["quantityPerDollar"] is None


@pytest.mark.parametrize(
    ("quantity", "unit", "normalized_value", "normalized_unit", "dimension"),
    [
        (2, "lb", 907184.74, "mg", "weight"),
        (500, "g", 500000, "mg", "weight"),
        (1.5, "L", 1500, "mL", "volume"),
        (2, "gal", 7570.823568, "mL", "volume"),
        (12, "count", 12, "count", "count"),
    ],
)
def test_product_exposes_dimension_safe_normalized_measurement(
    quantity, unit, normalized_value, normalized_unit, dimension
):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(
            f"/markets/{market['id']}/products",
            json={"name": "Measured", "price": 4, "quantity": quantity, "unit": unit},
        )
    assert response.status_code == 201
    product = response.json()
    assert product["quantity"] == quantity
    assert product["unit"] == unit
    assert product["normalizedQuantity"] == pytest.approx(normalized_value)
    assert product["normalizedUnit"] == normalized_unit
    assert product["quantityDimension"] == dimension
    assert product["normalizedQuantityPerDollar"] == pytest.approx(normalized_value / 4)


def test_unmeasured_product_has_no_normalized_values():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"])
    assert product["normalizedQuantity"] is None
    assert product["normalizedUnit"] is None
    assert product["quantityDimension"] is None
    assert product["normalizedQuantityPerDollar"] is None


def test_only_units_in_the_same_dimension_are_compatible():
    assert units_are_compatible("g", "lb")
    assert units_are_compatible("mL", "gal")
    assert units_are_compatible("count", "count")
    assert not units_are_compatible("lb", "L")
    assert not units_are_compatible("count", "g")
    assert not units_are_compatible(None, "g")


def test_normalization_rejects_incomplete_and_unknown_measurements():
    assert normalize_quantity(None, None) is None
    with pytest.raises(ValueError):
        normalize_quantity(1, None)
    with pytest.raises(ValueError):
        normalize_quantity(1, "stone")


@pytest.mark.parametrize(
    ("quantity", "unit"),
    [(2, "lb"), (500, "g"), (1.5, "L"), (12, "count"), (250, "mL"), (16, "oz")],
)
def test_product_can_store_a_valid_measurable_quantity(quantity, unit):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(
            f"/markets/{market['id']}/products",
            json={"name": f"Measured {unit}", "price": 3.99, "quantity": quantity, "unit": unit},
        )
    assert response.status_code == 201
    assert response.json()["quantity"] == quantity
    assert response.json()["unit"] == unit
    row = fetch_one("SELECT quantity_value, quantity_unit FROM market_products WHERE id = ?", (response.json()["id"],))
    assert row["quantity_value"] == quantity
    assert row["quantity_unit"] == unit


@pytest.mark.parametrize(
    "measurement",
    [
        {"quantity": 2},
        {"unit": "lb"},
        {"quantity": 0, "unit": "count"},
        {"quantity": -1, "unit": "g"},
        {"quantity": "2", "unit": "lb"},
        {"quantity": True, "unit": "count"},
        {"quantity": 2, "unit": "pound"},
    ],
)
def test_product_creation_rejects_incomplete_or_invalid_measurements(measurement):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(
            f"/markets/{market['id']}/products",
            json={"name": "Measured", "price": 3.99, **measurement},
        )
    assert response.status_code == 422
    assert fetch_one("SELECT 1 FROM market_products WHERE market_id = ?", (market["id"],)) is None


def test_static_product_photo_path_is_accepted():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(
            f"/markets/{market['id']}/products",
            json={"name": "Bread", "price": 2.5, "photoUrl": "/products/bread.jpg"},
        )
    assert response.status_code == 201
    assert response.json()["photoUrl"] == "/products/bread.jpg"


def test_anonymous_product_creation_is_rejected():
    with TestClient(app) as client:
        response = client.post(
            f"/markets/{uuid.uuid4()}/products", json={"name": "No Owner", "price": 1}
        )
    assert response.status_code == 401
    assert fetch_one("SELECT 1 FROM market_products WHERE name = 'No Owner'") is None


def test_owner_cannot_create_product_for_another_market():
    with TestClient(app) as client:
        _register(client)
        first_market = _market(client, "First")
        client.cookies.clear()
        _register(client)
        response = client.post(
            f"/markets/{first_market['id']}/products",
            json={"name": "Intruding Product", "price": 4.25},
        )
    assert response.status_code == 404
    assert fetch_one("SELECT 1 FROM market_products WHERE name = 'Intruding Product'") is None


def test_product_creation_rejects_unknown_market():
    with TestClient(app) as client:
        _register(client)
        response = client.post(
            f"/markets/{uuid.uuid4()}/products", json={"name": "Lost Product", "price": 1}
        )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"price": 1},
        {"name": "", "price": 1},
        {"name": "   ", "price": 1},
        {"name": "Apples"},
        {"name": "Apples", "price": -0.01},
        {"name": "Apples", "price": 1.001},
        {"name": "Apples", "price": "3.99"},
        {"name": "Apples", "price": True},
        {"name": "Apples", "price": 3.99, "photoUrl": "http://insecure.example/a.jpg"},
        {"name": "Apples", "price": 3.99, "photoUrl": "javascript:alert(1)"},
    ],
)
def test_invalid_product_is_rejected_without_writing(body):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(f"/markets/{market['id']}/products", json=body)
    assert response.status_code == 422
    assert fetch_one("SELECT 1 FROM market_products WHERE market_id = ?", (market["id"],)) is None


def test_client_cannot_override_product_market_relationship():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        response = client.post(
            f"/markets/{market['id']}/products",
            json={"name": "Apples", "price": 3.99, "marketId": str(uuid.uuid4())},
        )
    assert response.status_code == 422
    assert fetch_one("SELECT 1 FROM market_products WHERE market_id = ?", (market["id"],)) is None


def _product(client: TestClient, market_id: str, name: str = "Apples", price: float = 3.99) -> dict:
    response = client.post(
        f"/markets/{market_id}/products", json={"name": name, "price": price}
    )
    assert response.status_code == 201
    return response.json()


def test_owner_can_view_only_their_markets_products():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        first = _product(client, market["id"], "Apples")
        second = _product(client, market["id"], "Bread")
        products = client.get(f"/markets/{market['id']}/products")
        client.cookies.clear()
        _register(client)
        denied = client.get(f"/markets/{market['id']}/products")

    assert products.status_code == 200
    assert {product["id"] for product in products.json()} == {first["id"], second["id"]}
    assert denied.status_code == 404


def test_owner_can_edit_name_price_and_photo_without_changing_identity():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"], "Old Apples", 3.99)
        updated = client.patch(
            f"/markets/{market['id']}/products/{product['id']}",
            json={
                "name": "  New   Apples ",
                "price": 4.5,
                "photoUrl": "https://cdn.example.com/apples.jpg",
            },
        )
        cleared = client.patch(
            f"/markets/{market['id']}/products/{product['id']}", json={"photoUrl": None}
        )

    assert updated.status_code == 200
    assert updated.json() | {"createdAt": product["createdAt"]} == {
        **product,
        "name": "New Apples",
        "price": 4.5,
        "priceCents": 450,
        "photoUrl": "https://cdn.example.com/apples.jpg",
    }
    assert cleared.status_code == 200
    assert cleared.json()["photoUrl"] is None
    assert cleared.json()["id"] == product["id"]
    assert cleared.json()["marketId"] == market["id"]


def test_owner_can_add_edit_and_clear_product_measurement():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"])
        measured = client.patch(
            f"/markets/{market['id']}/products/{product['id']}",
            json={"quantity": 2, "unit": "lb"},
        )
        adjusted = client.patch(
            f"/markets/{market['id']}/products/{product['id']}", json={"quantity": 1.5}
        )
        renamed_unit = client.patch(
            f"/markets/{market['id']}/products/{product['id']}", json={"unit": "kg"}
        )
        cleared = client.patch(
            f"/markets/{market['id']}/products/{product['id']}",
            json={"quantity": None, "unit": None},
        )

    assert measured.status_code == 200
    assert measured.json()["quantity"] == 2
    assert measured.json()["unit"] == "lb"
    assert adjusted.status_code == 200
    assert adjusted.json()["quantity"] == 1.5
    assert adjusted.json()["unit"] == "lb"
    assert renamed_unit.status_code == 200
    assert renamed_unit.json()["quantity"] == 1.5
    assert renamed_unit.json()["unit"] == "kg"
    assert cleared.status_code == 200
    assert cleared.json()["quantity"] is None
    assert cleared.json()["unit"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"quantity": None},
        {"unit": None},
        {"quantity": 0, "unit": "count"},
        {"quantity": 2, "unit": "pound"},
    ],
)
def test_incomplete_measurement_edit_does_not_mutate_product(body):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = client.post(
            f"/markets/{market['id']}/products",
            json={"name": "Apples", "price": 3.99, "quantity": 2, "unit": "lb"},
        ).json()
        response = client.patch(f"/markets/{market['id']}/products/{product['id']}", json=body)
    assert response.status_code == 422
    row = fetch_one(
        "SELECT quantity_value, quantity_unit FROM market_products WHERE id = ?", (product["id"],)
    )
    assert dict(row) == {"quantity_value": 2, "quantity_unit": "lb"}


@pytest.mark.parametrize("body", [{"quantity": 2}, {"unit": "lb"}])
def test_measurement_edit_requires_a_complete_pair_for_unmeasured_product(body):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"])
        response = client.patch(f"/markets/{market['id']}/products/{product['id']}", json=body)
    assert response.status_code == 422
    row = fetch_one(
        "SELECT quantity_value, quantity_unit FROM market_products WHERE id = ?", (product["id"],)
    )
    assert dict(row) == {"quantity_value": None, "quantity_unit": None}


def test_market_product_quantity_columns_migrate_feature_five_database(tmp_path, monkeypatch):
    old_db = tmp_path / "feature-five.db"
    conn = sqlite3.connect(old_db)
    conn.executescript(
        """
        CREATE TABLE accounts (
            id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            role TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE markets (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_account_id TEXT NOT NULL,
            primary_color TEXT NOT NULL, logo_url TEXT, created_at TEXT NOT NULL
        );
        CREATE TABLE market_products (
            id TEXT PRIMARY KEY, market_id TEXT NOT NULL, name TEXT NOT NULL,
            price_cents INTEGER NOT NULL, photo_url TEXT, created_at TEXT NOT NULL
        );
        INSERT INTO accounts VALUES ('owner', 'owner@example.com', 'unused', 'MARKET_OWNER', 'now');
        INSERT INTO markets VALUES ('market', 'Existing Market', 'owner', '#126B5B', NULL, 'now');
        INSERT INTO market_products VALUES ('product', 'market', 'Existing Product', 399, NULL, 'now');
        """
    )
    conn.close()
    import api.db as merchant_db

    monkeypatch.setattr(merchant_db, "MERCHANT_DB", old_db)
    merchant_db.init_db()

    row = merchant_db.fetch_one(
        "SELECT quantity_value, quantity_unit FROM market_products WHERE id = 'product'"
    )
    assert dict(row) == {"quantity_value": None, "quantity_unit": None}


def test_database_rejects_invalid_market_product_measurements():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)

    with pytest.raises(sqlite3.IntegrityError):
        with transaction() as conn:
            conn.execute(
                "INSERT INTO market_products "
                "(id, market_id, name, price_cents, quantity_value, quantity_unit, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), market["id"], "Broken", 399, 2, None, "now"),
            )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"name": "   "},
        {"price": None},
        {"price": -1},
        {"price": 1.001},
        {"price": "4.50"},
        {"photoUrl": "http://insecure.example/apple.jpg"},
        {"marketId": str(uuid.uuid4())},
    ],
)
def test_invalid_product_edit_does_not_mutate_product(body):
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"])
        response = client.patch(f"/markets/{market['id']}/products/{product['id']}", json=body)
    assert response.status_code == 422
    row = fetch_one("SELECT name, price_cents, photo_url FROM market_products WHERE id = ?", (product["id"],))
    assert dict(row) == {"name": "Apples", "price_cents": 399, "photo_url": None}


def test_another_owner_cannot_edit_or_remove_product_from_other_market():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"])
        client.cookies.clear()
        _register(client)
        edit = client.patch(
            f"/markets/{market['id']}/products/{product['id']}", json={"price": 1}
        )
        removal = client.delete(f"/markets/{market['id']}/products/{product['id']}")

    assert edit.status_code == 404
    assert removal.status_code == 404
    assert fetch_one("SELECT 1 FROM market_products WHERE id = ?", (product["id"],)) is not None


def test_owner_can_remove_product_and_cannot_remove_it_twice():
    with TestClient(app) as client:
        _register(client)
        market = _market(client)
        product = _product(client, market["id"])
        removed = client.delete(f"/markets/{market['id']}/products/{product['id']}")
        second = client.delete(f"/markets/{market['id']}/products/{product['id']}")

    assert removed.status_code == 204
    assert fetch_one("SELECT 1 FROM market_products WHERE id = ?", (product["id"],)) is None
    assert second.status_code == 404


def test_anonymous_product_management_is_rejected():
    product_id = str(uuid.uuid4())
    market_id = str(uuid.uuid4())
    with TestClient(app) as client:
        listed = client.get(f"/markets/{market_id}/products")
        edited = client.patch(f"/markets/{market_id}/products/{product_id}", json={"name": "Nope"})
        removed = client.delete(f"/markets/{market_id}/products/{product_id}")
    assert listed.status_code == 401
    assert edited.status_code == 401
    assert removed.status_code == 401
