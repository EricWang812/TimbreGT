"""The storefront checkout records a signed-in buyer's purchase as market orders.

Regression: purchases went through /checkout/confirm and /checkout/complete, which
wrote only the legacy receipt, so they never reached the buyer's order history or
the seller's dashboard. The issuer boundary (§2.5) must stay exactly as it was.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from api import issuer_client
from api.db import fetch_all
from api.main import app

PASSWORD = "correct horse battery"
PICKUP = {"addressLine1": "1 Boardwalk Way", "city": "Tybee Island", "stateRegion": "GA",
          "postalCode": "31328", "country": "United States"}
HOME = {"recipientName": "Ada Lovelace", "addressLine1": "12 Main Street", "city": "Boston",
        "stateRegion": "MA", "postalCode": "02110", "country": "United States"}


@pytest.fixture
def issuer(monkeypatch):
    calls = {"sessions": 0, "verified": True}
    def create_session(instruction_id, amount, merchant_id):
        calls["sessions"] += 1
        calls["amount"] = amount
        return "issuer-session"
    monkeypatch.setattr(issuer_client, "create_session", create_session)
    monkeypatch.setattr(issuer_client, "approve", lambda instruction_id: (
        {"verified": True, "transaction_id": f"txn-{instruction_id[:8]}"} if calls["verified"]
        else {"verified": False, "transaction_id": None}))
    return calls


def register(client, role):
    email = f"{role}-{uuid.uuid4()}@example.com"
    response = client.post(f"/{'buyer' if role == 'buyer' else 'market'}-auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return email


def seller_market(client, name="Harbor Market", ship=True, pickup=True):
    register(client, "owner")
    market = client.post("/markets", json={"name": name}).json()
    product = client.post(f"/markets/{market['id']}/products",
                          json={"name": "Fuji Apples", "price": 3.99, "quantity": 2, "unit": "lb"}).json()
    if ship:
        assert client.patch(f"/markets/{market['id']}/shipping-settings",
                            json={"shippingEnabled": True, "supportedShippingMethods": ["UPS"]}).status_code == 200
    if pickup:
        assert client.patch(f"/markets/{market['id']}/pickup-settings",
                            json={"pickupEnabled": True, "pickupAddress": PICKUP}).status_code == 200
    return market, product


def buy(client, lines, fulfillment=None):
    body = {"items": [{"product_id": pid, "quantity": q} for pid, q in lines]}
    if fulfillment is not None:
        body["fulfillment"] = fulfillment
    return client.post("/checkout/confirm", json=body)


def test_buyer_purchase_reaches_buyer_history_and_seller_dashboard(issuer):
    with TestClient(app) as c:
        market, product = seller_market(c)
        register(c, "buyer")   # same browser: owner and buyer sessions use separate cookies
        address = c.post("/buyer/addresses", json=HOME).json()

        assert buy(c, [(product["id"], 2)]).status_code == 422       # must choose ship or pickup
        assert issuer["sessions"] == 0                                # and no payment was opened
        confirmed = buy(c, [(product["id"], 2)], {"method": "SHIP", "shippingAddressId": address["id"]})
        assert confirmed.status_code == 200 and confirmed.json()["savedToAccount"] is True
        paid_total = confirmed.json()["total_cents"]
        assert issuer["amount"] == paid_total
        assert c.get("/buyer/markets/orders").json()["orders"] == []  # nothing before the bank approves

        completed = c.post("/checkout/complete", json={"instruction_id": confirmed.json()["instruction_id"]})
        assert set(completed.json()) == {"verified", "transaction_id"} and completed.json()["verified"]

        history = c.get("/buyer/markets/orders").json()["orders"]
        assert len(history) == 1
        order = history[0]
        assert order["market"]["name"] == "Harbor Market" and order["status"] == "NOT_STARTED"
        assert order["totalCents"] == paid_total                      # tax and shipping included
        assert order["items"][0]["product_name"] == "Fuji Apples" and order["items"][0]["amount"] == 2
        detail = c.get(f"/buyer/markets/orders/{order['id']}").json()
        assert detail["fulfillmentMethod"] == "SHIP" and detail["shippingAddress"]["recipientName"] == "Ada Lovelace"

        board = c.get(f"/markets/{market['id']}/orders").json()["orders"]
        assert [o["id"] for o in board] == [order["id"]]
        assert "buyerAccountId" not in board[0] and "transactionId" not in board[0]
        for status in ("FULFILLING", "ORDER_COMPLETE", "SHIPPING"):
            assert c.patch(f"/markets/{market['id']}/orders/{order['id']}/status", json={"status": status}).status_code == 200
        assert c.patch(f"/markets/{market['id']}/orders/{order['id']}/tracking",
                       json={"carrier": "UPS", "trackingNumber": "1Z999"}).status_code == 200
        detail = c.get(f"/buyer/markets/orders/{order['id']}").json()
        assert detail["status"] == "SHIPPING" and detail["trackingNumber"] == "1Z999"
        assert c.get(f"/markets/{market['id']}/analytics?period=7D").json()["orderCount"] == 1
        insights = c.get(f"/markets/{market['id']}/insights").json()
        assert insights["orderCount"] == 1 and insights["status"] == "insufficient_data"   # one shipped order supports no pattern


def test_pickup_order_uses_the_markets_pickup_address(issuer):
    with TestClient(app) as c:
        _, product = seller_market(c)
        register(c, "buyer")
        confirmed = buy(c, [(product["id"], 1)], {"method": "PICKUP"})
        c.post("/checkout/complete", json={"instruction_id": confirmed.json()["instruction_id"]})
        order = c.get("/buyer/markets/orders").json()["orders"][0]
        detail = c.get(f"/buyer/markets/orders/{order['id']}").json()
        assert detail["fulfillmentMethod"] == "PICKUP" and detail["pickupAddress"]["city"] == "Tybee Island"


def test_unavailable_method_or_foreign_address_opens_no_payment(issuer):
    with TestClient(app) as c:
        _, product = seller_market(c, ship=False)
        register(c, "buyer")
        own = c.post("/buyer/addresses", json=HOME).json()
        assert buy(c, [(product["id"], 1)], {"method": "SHIP", "shippingAddressId": own["id"]}).status_code == 409
        c.cookies.clear()
        register(c, "buyer")
        assert buy(c, [(product["id"], 1)], {"method": "SHIP", "shippingAddressId": own["id"]}).status_code == 422
        assert buy(c, [(product["id"], 1)], {"method": "PICKUP", "shippingAddressId": own["id"]}).status_code == 422
        assert issuer["sessions"] == 0


def test_guest_checkout_is_unchanged_and_unverified_payment_creates_nothing(issuer):
    with TestClient(app) as c:
        _, product = seller_market(c)
        c.cookies.clear()
        guest = buy(c, [(product["id"], 1)])
        assert guest.status_code == 200 and guest.json()["savedToAccount"] is False
        done = c.post("/checkout/complete", json={"instruction_id": guest.json()["instruction_id"]})
        assert set(done.json()) == {"verified", "transaction_id"}
        assert fetch_all("SELECT 1 FROM market_checkout_sessions WHERE authorization_instruction_id = ?",
                         (guest.json()["instruction_id"],)) == []

        register(c, "buyer")
        issuer["verified"] = False
        declined = buy(c, [(product["id"], 1)], {"method": "PICKUP"})
        result = c.post("/checkout/complete", json={"instruction_id": declined.json()["instruction_id"]}).json()
        assert result == {"verified": False, "transaction_id": None}
        assert c.get("/buyer/markets/orders").json()["orders"] == []


def test_one_payment_across_two_markets_splits_into_orders_that_add_up(issuer):
    with TestClient(app) as c:
        first, apples = seller_market(c, "First Market")
        c.cookies.clear()
        second, pears = seller_market(c, "Second Market")
        c.cookies.clear()
        register(c, "buyer")
        confirmed = buy(c, [(apples["id"], 3), (pears["id"], 1)], {"method": "PICKUP"})
        c.post("/checkout/complete", json={"instruction_id": confirmed.json()["instruction_id"]})
        orders = c.get("/buyer/markets/orders").json()["orders"]
        assert sorted(o["market"]["name"] for o in orders) == ["First Market", "Second Market"]
        assert sum(o["totalCents"] for o in orders) == confirmed.json()["total_cents"]
        assert issuer["sessions"] == 1


def test_pickup_waives_shipping_only_for_a_recorded_pickup_order(issuer):
    with TestClient(app) as c:
        _, product = seller_market(c)
        c.cookies.clear()
        items = [{"product_id": product["id"], "quantity": 1}]
        shipped = c.post("/cart/quote", json={"items": items}).json()
        assert shipped["shipping_cents"] > 0                         # $3.99 is under the free-shipping minimum
        assert c.post("/cart/quote", json={"items": items, "fulfillmentMethod": "PICKUP"}).json()["shipping_cents"] == 0
        guest = buy(c, [(product["id"], 1)], {"method": "PICKUP"})    # a guest claiming pickup still pays shipping
        assert guest.json()["shipping_cents"] == shipped["shipping_cents"] and guest.json()["savedToAccount"] is False

        register(c, "buyer")
        pickup = buy(c, [(product["id"], 1)], {"method": "PICKUP"})
        assert pickup.json()["shipping_cents"] == 0
        assert pickup.json()["total_cents"] == shipped["total_cents"] - shipped["shipping_cents"]
        assert issuer["amount"] == pickup.json()["total_cents"]      # the bank approves the pickup total
        c.post("/checkout/complete", json={"instruction_id": pickup.json()["instruction_id"]})
        assert c.get("/buyer/markets/orders").json()["orders"][0]["totalCents"] == pickup.json()["total_cents"]


def test_seller_created_product_appears_in_the_storefront_and_can_be_bought(issuer):
    with TestClient(app) as c:
        register(c, "owner")
        market = c.post("/markets", json={"name": "Dockside Deli"}).json()
        made = c.post(f"/markets/{market['id']}/products", json={
            "name": "Smoked Salmon", "price": 12.5, "brand": "  Dockside  ", "category": "Seafood",
            "photoUrl": "/products/example.jpg", "quantity": 8, "unit": "oz"})
        assert made.status_code == 201
        product = made.json()
        assert product["brand"] == "Dockside" and product["category"] == "seafood"
        edited = c.patch(f"/markets/{market['id']}/products/{product['id']}", json={"category": "", "brand": "Dock"}).json()
        assert edited["category"] is None and edited["brand"] == "Dock"

        c.cookies.clear()   # a buyer's view: public storefront
        listed = c.get(f"/storefront/markets/{market['id']}/products").json()["products"]
        assert [p["name"] for p in listed] == ["Smoked Salmon"] and listed[0]["brand"] == "Dock"
        quote = c.post("/cart/quote", json={"items": [{"product_id": product["id"], "quantity": 2}]}).json()
        assert quote["subtotal_cents"] == 2500
