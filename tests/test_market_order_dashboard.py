"""Feature 16 owner dashboard authorization and order isolation."""
import uuid
from fastapi.testclient import TestClient
from api.db import transaction
from api.main import app


def _owner(client):
    return client.post("/market-auth/register", json={"email": f"dashboard-{uuid.uuid4()}@example.com", "password": "correct horse battery"})


def test_owner_sees_only_its_market_orders_and_other_owner_cannot_read():
    with TestClient(app) as client:
        owner = _owner(client).json()
        market = client.post("/markets", json={"name": "Dashboard Market"}).json()
        with transaction() as conn:
            conn.execute("INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES ('dash-session', 'dash-session', ?, ?, '[]', 100, 100, 'PICKUP', NULL, '{}', 'now')", (owner["id"], market["id"]))
            conn.execute("INSERT INTO market_orders (id, instruction_id, buyer_account_id, market_id, subtotal_cents, total_cents, fulfillment_method, status, transaction_id, shipping_address_json, pickup_address_json, created_at, updated_at) VALUES ('dash-order', 'dash-session', ?, ?, 100, 100, 'PICKUP', 'NOT_STARTED', 'txn', NULL, '{}', 'now', 'now')", (owner["id"], market["id"]))
            conn.execute("INSERT INTO market_order_items VALUES ('dash-item', 'dash-order', 'p', 'Apples', 100, 1, NULL, NULL)")
        dashboard = client.get(f"/markets/{market['id']}/orders")
        client.cookies.clear()
        _owner(client)
        forbidden = client.get(f"/markets/{market['id']}/orders")
    assert dashboard.status_code == 200
    assert dashboard.json()["orders"][0]["items"][0]["product_name"] == "Apples"
    assert forbidden.status_code == 404


def test_owner_status_machine_requires_ordered_pickup_transitions():
    with TestClient(app) as client:
        owner = _owner(client).json()
        market = client.post("/markets", json={"name": "Status Market"}).json()
        with transaction() as conn:
            conn.execute("INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES ('status-session', 'status-session', ?, ?, '[]', 100, 100, 'PICKUP', NULL, '{}', 'now')", (owner["id"], market["id"]))
            conn.execute("INSERT INTO market_orders (id, instruction_id, buyer_account_id, market_id, subtotal_cents, total_cents, fulfillment_method, status, transaction_id, shipping_address_json, pickup_address_json, created_at, updated_at) VALUES ('status-order', 'status-session', ?, ?, 100, 100, 'PICKUP', 'NOT_STARTED', 'txn', NULL, '{}', 'now', 'now')", (owner["id"], market["id"]))
        assert client.patch(f"/markets/{market['id']}/orders/status-order/status", json={"status": "SHIPPING"}).status_code == 422
        assert client.patch(f"/markets/{market['id']}/orders/status-order/status", json={"status": "FULFILLING"}).json()["status"] == "FULFILLING"
        current = client.get(f"/markets/{market['id']}/orders").json()["orders"][0]
        assert current["allowedTransitions"] == ["ORDER_COMPLETE"]
        assert current["statusHistory"][-1]["status"] == "FULFILLING"
        assert current["stageSince"] == current["statusHistory"][-1]["enteredAt"]
        assert client.patch(f"/markets/{market['id']}/orders/status-order/status", json={"status": "ORDER_COMPLETE"}).json()["status"] == "ORDER_COMPLETE"
        done = client.patch(f"/markets/{market['id']}/orders/status-order/status", json={"status": "READY_FOR_PICKUP"})
    assert done.json()["status"] == "READY_FOR_PICKUP"


def test_owner_can_add_carrier_tracking_only_to_shipping_order():
    with TestClient(app) as client:
        owner = _owner(client).json()
        market = client.post("/markets", json={"name": "Tracking Market"}).json()
        with transaction() as conn:
            conn.execute("INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES ('tracking-session', 'tracking-session', ?, ?, '[]', 100, 100, 'SHIP', '{}', NULL, 'now')", (owner["id"], market["id"]))
            conn.execute("INSERT INTO market_orders (id, instruction_id, buyer_account_id, market_id, subtotal_cents, total_cents, fulfillment_method, status, transaction_id, shipping_address_json, pickup_address_json, created_at, updated_at) VALUES ('tracking-order', 'tracking-session', ?, ?, 100, 100, 'SHIP', 'NOT_STARTED', 'txn', '{}', NULL, 'now', 'now')", (owner["id"], market["id"]))
        updated = client.patch(f"/markets/{market['id']}/orders/tracking-order/tracking", json={"carrier": "UPS", "trackingNumber": "1Z123"})
    assert updated.json() == {"id": "tracking-order", "carrier": "UPS", "trackingNumber": "1Z123"}


def test_owner_can_mark_shipping_order_for_local_driver_without_tracking():
    with TestClient(app) as client:
        owner = _owner(client).json()
        market = client.post("/markets", json={"name": "Local Driver Market"}).json()
        with transaction() as conn:
            conn.execute("INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES ('local-session', 'local-session', ?, ?, '[]', 100, 100, 'SHIP', '{}', NULL, 'now')", (owner["id"], market["id"]))
            conn.execute("INSERT INTO market_orders (id, instruction_id, buyer_account_id, market_id, subtotal_cents, total_cents, fulfillment_method, status, transaction_id, shipping_address_json, pickup_address_json, created_at, updated_at) VALUES ('local-order', 'local-session', ?, ?, 100, 100, 'SHIP', 'NOT_STARTED', 'txn', '{}', NULL, 'now', 'now')", (owner["id"], market["id"]))
        updated = client.patch(f"/markets/{market['id']}/orders/local-order/local-driver")
        dashboard = client.get(f"/markets/{market['id']}/orders")
    assert updated.json()["localDriver"] is True
    assert dashboard.json()["orders"][0]["deliveryMessage"] == "A local driver is handling this delivery."


def test_buyer_history_is_private_and_includes_market_order_summary():
    with TestClient(app) as client:
        buyer = client.post("/buyer-auth/register", json={"email": f"history-{uuid.uuid4()}@example.com", "password": "correct horse battery"}).json()
        client.cookies.clear()
        _owner(client)
        market = client.post("/markets", json={"name": "History Market"}).json()
        with transaction() as conn:
            conn.execute("INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES ('history-session', 'history-session', ?, ?, '[]', 100, 100, 'PICKUP', NULL, '{}', 'now')", (buyer["id"], market["id"]))
            conn.execute("INSERT INTO market_orders (id, instruction_id, buyer_account_id, market_id, subtotal_cents, total_cents, fulfillment_method, status, transaction_id, shipping_address_json, pickup_address_json, created_at, updated_at) VALUES ('history-order', 'history-session', ?, ?, 100, 100, 'PICKUP', 'NOT_STARTED', 'txn', NULL, '{}', 'now', 'now')", (buyer["id"], market["id"]))
            conn.execute("INSERT INTO market_order_items VALUES ('history-item', 'history-order', 'p', 'Apples', 100, 1, NULL, NULL)")
        client.cookies.clear()
        client.post("/buyer-auth/login", json={"email": buyer["email"], "password": "correct horse battery"})
        history = client.get("/buyer/markets/orders")
        client.cookies.clear()
        client.post("/buyer-auth/register", json={"email": f"other-{uuid.uuid4()}@example.com", "password": "correct horse battery"})
        other = client.get("/buyer/markets/orders")
    assert history.json()["orders"][0]["market"]["name"] == "History Market"
    assert history.json()["orders"][0]["items"][0]["product_name"] == "Apples"
    assert other.json() == {"orders": []}


def test_buyer_can_view_own_order_details_but_not_another_buyers():
    with TestClient(app) as client:
        buyer = client.post("/buyer-auth/register", json={"email": f"detail-{uuid.uuid4()}@example.com", "password": "correct horse battery"}).json()
        client.cookies.clear()
        _owner(client)
        market = client.post("/markets", json={"name": "Detail Market"}).json()
        with transaction() as conn:
            conn.execute("INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES ('detail-session', 'detail-session', ?, ?, '[]', 100, 100, 'SHIP', '{}', NULL, 'now')", (buyer["id"], market["id"]))
            conn.execute("INSERT INTO market_orders (id, instruction_id, buyer_account_id, market_id, subtotal_cents, total_cents, fulfillment_method, status, transaction_id, shipping_address_json, pickup_address_json, carrier, tracking_number, local_driver, created_at, updated_at) VALUES ('detail-order', 'detail-session', ?, ?, 100, 100, 'SHIP', 'NOT_STARTED', 'txn', '{}', NULL, 'UPS', '1Z123', 0, 'now', 'now')", (buyer["id"], market["id"]))
            conn.execute("INSERT INTO market_order_items VALUES ('detail-item', 'detail-order', 'p', 'Apples', 100, 1, NULL, NULL)")
        client.cookies.clear()
        client.post("/buyer-auth/login", json={"email": buyer["email"], "password": "correct horse battery"})
        detail = client.get("/buyer/markets/orders/detail-order")
        client.cookies.clear()
        client.post("/buyer-auth/register", json={"email": f"outsider-{uuid.uuid4()}@example.com", "password": "correct horse battery"})
        forbidden = client.get("/buyer/markets/orders/detail-order")
    assert detail.json()["trackingNumber"] == "1Z123"
    assert detail.json()["shippingAddress"] == {}
    assert forbidden.status_code == 404
