"""Market-aware order confirmation that reuses the existing issuer approval boundary.

The legacy catalog checkout remains separate. This route prices only products from
one market, snapshots them with the buyer's saved fulfillment choice, and creates
the durable market order only after the issuer confirms payment authorization.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from api import issuer_client
from api.buyer_auth import Buyer
from api.config import MAX_CART_LINES, MAX_QUANTITY, MERCHANT_ID
from api.db import transaction
from api.market_auth import MarketOwner

log = logging.getLogger(__name__)
router = APIRouter(prefix="/buyer/markets", tags=["market orders"])
owner_router = APIRouter(prefix="/markets", tags=["market orders"])


class MarketOrderLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    productId: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=MAX_QUANTITY)


class ConfirmMarketCheckout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MarketOrderLine] = Field(min_length=1, max_length=MAX_CART_LINES)


class MarketCheckoutConfirmation(BaseModel):
    instructionId: str
    sessionId: str
    subtotalCents: int
    totalCents: int
    fulfillmentMethod: str


class MultiMarketOrderLine(MarketOrderLine):
    marketId: str = Field(min_length=1, max_length=64)


class ConfirmMultiMarketCheckout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MultiMarketOrderLine] = Field(min_length=1, max_length=MAX_CART_LINES)


class MarketCheckoutSplit(BaseModel):
    marketId: str
    subtotalCents: int
    fulfillmentMethod: str


class MultiMarketCheckoutConfirmation(BaseModel):
    instructionId: str
    sessionId: str
    totalCents: int
    orders: list[MarketCheckoutSplit]


OrderStatus = Literal["NOT_STARTED", "FULFILLING", "ORDER_COMPLETE", "SHIPPING", "READY_FOR_PICKUP"]


class UpdateOrderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: OrderStatus


class UpdateTracking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    carrier: Literal["USPS", "UPS", "FEDEX"]
    trackingNumber: str = Field(min_length=1, max_length=128)


_VALID_TRANSITIONS = {
    "NOT_STARTED": {"FULFILLING"},
    "FULFILLING": {"ORDER_COMPLETE"},
    "ORDER_COMPLETE": {"SHIPPING", "READY_FOR_PICKUP"},
    "SHIPPING": set(),
    "READY_FOR_PICKUP": set(),
}


def _address_snapshot(row) -> dict:
    return {
        "recipientName": row["recipient_name"],
        "addressLine1": row["address_line_1"],
        "addressLine2": row["address_line_2"],
        "city": row["city"],
        "stateRegion": row["state_region"],
        "postalCode": row["postal_code"],
        "country": row["country"],
    }


def _pickup_snapshot(row) -> dict:
    return {
        "addressLine1": row["address_line_1"],
        "addressLine2": row["address_line_2"],
        "city": row["city"],
        "stateRegion": row["state_region"],
        "postalCode": row["postal_code"],
        "country": row["country"],
    }


def _priced_market_lines(conn, market_id: str, body: ConfirmMarketCheckout) -> tuple[list[dict], int]:
    product_ids = [line.productId for line in body.items]
    if len(product_ids) != len(set(product_ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "each product may appear only once")
    marks = ", ".join("?" for _ in product_ids)
    rows = conn.execute(
        f"SELECT id, name, price_cents, quantity_value, quantity_unit FROM market_products "
        f"WHERE market_id = ? AND id IN ({marks})",
        (market_id, *product_ids),
    ).fetchall()
    products = {row["id"]: row for row in rows}
    unknown = [product_id for product_id in product_ids if product_id not in products]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "market products not found")
    lines = []
    for request_line in body.items:
        product = products[request_line.productId]
        lines.append({
            "productId": product["id"],
            "productName": product["name"],
            "priceCents": product["price_cents"],
            "amount": request_line.quantity,
            "quantityValue": product["quantity_value"],
            "quantityUnit": product["quantity_unit"],
        })
    return lines, sum(line["priceCents"] * line["amount"] for line in lines)


def _prepare_market_checkout(conn, market_id: str, body: ConfirmMarketCheckout, buyer: Buyer) -> dict:
    if conn.execute("SELECT 1 FROM markets WHERE id = ?", (market_id,)).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market not found")
    selection = conn.execute(
        "SELECT fulfillment_method, shipping_address_id FROM buyer_market_fulfillment_selections "
        "WHERE buyer_account_id = ? AND market_id = ?", (buyer.id, market_id)
    ).fetchone()
    if selection is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "select shipping or pickup before checkout")
    lines, subtotal_cents = _priced_market_lines(conn, market_id, body)
    shipping_snapshot = pickup_snapshot = None
    if selection["fulfillment_method"] == "SHIP":
        address = conn.execute("SELECT * FROM buyer_addresses WHERE id = ? AND buyer_account_id = ?", (selection["shipping_address_id"], buyer.id)).fetchone()
        if address is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "shipping address not found")
        shipping_snapshot = _address_snapshot(address)
    else:
        pickup = conn.execute("SELECT * FROM market_pickup_addresses WHERE market_id = ?", (market_id,)).fetchone()
        if pickup is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "pickup is unavailable")
        pickup_snapshot = _pickup_snapshot(pickup)
    return {"marketId": market_id, "lines": lines, "subtotalCents": subtotal_cents,
            "fulfillmentMethod": selection["fulfillment_method"], "shipping": shipping_snapshot, "pickup": pickup_snapshot}


@router.post("/{market_id}/checkout/confirm", response_model=MarketCheckoutConfirmation)
def confirm_market_checkout(
    market_id: str, body: ConfirmMarketCheckout, buyer: Buyer
) -> MarketCheckoutConfirmation:
    with transaction() as conn:
        prepared = _prepare_market_checkout(conn, market_id, body, buyer)

    # This is the existing server-to-server issuer session. No market route can
    # declare itself paid or create an order without its verified result.
    instruction_id = str(uuid.uuid4())
    try:
        session_id = issuer_client.create_session(instruction_id, prepared["subtotalCents"], MERCHANT_ID)
    except issuer_client.IssuerError as exc:
        log.exception("issuer session creation failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "payment service unavailable") from exc

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with transaction() as conn:
        conn.execute(
            "INSERT INTO market_checkout_sessions "
            "(instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, "
            "fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (instruction_id, instruction_id, buyer.id, market_id, json.dumps(prepared["lines"]), prepared["subtotalCents"], prepared["subtotalCents"],
             prepared["fulfillmentMethod"], json.dumps(prepared["shipping"]) if prepared["shipping"] else None,
             json.dumps(prepared["pickup"]) if prepared["pickup"] else None, now),
        )
    return MarketCheckoutConfirmation(
        instructionId=instruction_id,
        sessionId=session_id,
        subtotalCents=prepared["subtotalCents"], totalCents=prepared["subtotalCents"], fulfillmentMethod=prepared["fulfillmentMethod"],
    )


@router.post("/checkout/confirm", response_model=MultiMarketCheckoutConfirmation)
def confirm_multi_market_checkout(body: ConfirmMultiMarketCheckout, buyer: Buyer) -> MultiMarketCheckoutConfirmation:
    grouped: dict[str, list[MarketOrderLine]] = {}
    seen: set[tuple[str, str]] = set()
    for line in body.items:
        key = (line.marketId, line.productId)
        if key in seen:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "each market product may appear only once")
        seen.add(key)
        grouped.setdefault(line.marketId, []).append(MarketOrderLine(productId=line.productId, quantity=line.quantity))
    with transaction() as conn:
        prepared = [_prepare_market_checkout(conn, market_id, ConfirmMarketCheckout(items=lines), buyer) for market_id, lines in grouped.items()]
    total_cents = sum(item["subtotalCents"] for item in prepared)
    instruction_id = str(uuid.uuid4())
    try:
        session_id = issuer_client.create_session(instruction_id, total_cents, MERCHANT_ID)
    except issuer_client.IssuerError as exc:
        log.exception("issuer session creation failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "payment service unavailable") from exc
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with transaction() as conn:
        for item in prepared:
            conn.execute(
                "INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id, market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json, pickup_address_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), instruction_id, buyer.id, item["marketId"], json.dumps(item["lines"]), item["subtotalCents"], item["subtotalCents"], item["fulfillmentMethod"], json.dumps(item["shipping"]) if item["shipping"] else None, json.dumps(item["pickup"]) if item["pickup"] else None, now),
            )
    return MultiMarketCheckoutConfirmation(instructionId=instruction_id, sessionId=session_id, totalCents=total_cents,
        orders=[MarketCheckoutSplit(marketId=item["marketId"], subtotalCents=item["subtotalCents"], fulfillmentMethod=item["fulfillmentMethod"]) for item in prepared])


def materialize_market_order(conn, instruction_id: str, transaction_id: str) -> None:
    """Insert an immutable market order only after the issuer verified payment."""
    sessions = conn.execute("SELECT * FROM market_checkout_sessions WHERE authorization_instruction_id = ?", (instruction_id,)).fetchall()
    for session in sessions:
        if conn.execute("SELECT 1 FROM market_orders WHERE instruction_id = ?", (session["instruction_id"],)).fetchone() is not None:
            continue
        order_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
        "INSERT INTO market_orders "
        "(id, instruction_id, buyer_account_id, market_id, subtotal_cents, total_cents, fulfillment_method, "
        "status, transaction_id, shipping_address_json, pickup_address_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'NOT_STARTED', ?, ?, ?, ?, ?)",
        (order_id, session["instruction_id"], session["buyer_account_id"], session["market_id"],
         session["subtotal_cents"], session["total_cents"], session["fulfillment_method"], transaction_id,
         session["shipping_address_json"], session["pickup_address_json"], now, now),
        )
        for line in json.loads(session["items_json"]):
            conn.execute(
            "INSERT INTO market_order_items "
            "(id, order_id, product_id, product_name, price_cents, amount, quantity_value, quantity_unit) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), order_id, line["productId"], line["productName"], line["priceCents"],
                 line["amount"], line["quantityValue"], line["quantityUnit"]),
            )


@owner_router.get("/{market_id}/orders")
def market_order_dashboard(market_id: str, owner: MarketOwner) -> dict:
    """Return only the authenticated owner's fulfillment work for one market."""
    with transaction() as conn:
        if conn.execute(
            "SELECT 1 FROM markets WHERE id = ? AND owner_account_id = ?", (market_id, owner.id)
        ).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "market not found")
        orders = conn.execute(
            "SELECT * FROM market_orders WHERE market_id = ? ORDER BY created_at DESC", (market_id,)
        ).fetchall()
        result = []
        for order in orders:
            items = conn.execute(
                "SELECT product_id, product_name, price_cents, amount, quantity_value, quantity_unit "
                "FROM market_order_items WHERE order_id = ? ORDER BY id", (order["id"],)
            ).fetchall()
            history = conn.execute("SELECT status, entered_at FROM market_order_status_history WHERE order_id = ? ORDER BY id", (order["id"],)).fetchall()
            stage_since = history[-1]["entered_at"] if history else (order["created_at"] if order["fulfillment_status"] == "NOT_STARTED" else None)
            result.append({
                "stageSince": stage_since,
                "statusHistory": [{"status": h["status"], "enteredAt": h["entered_at"]} for h in history],
                "id": order["id"], "marketId": order["market_id"], "items": [dict(item) for item in items],
                "totalCents": order["total_cents"], "fulfillmentMethod": order["fulfillment_method"],
                "status": order["fulfillment_status"], "allowedTransitions": [s for s in sorted(_VALID_TRANSITIONS[order["fulfillment_status"]]) if s not in {"SHIPPING", "READY_FOR_PICKUP"} or s == ("SHIPPING" if order["fulfillment_method"] == "SHIP" else "READY_FOR_PICKUP")], "shippingAddress": json.loads(order["shipping_address_json"]) if order["shipping_address_json"] else None,
                "pickupAddress": json.loads(order["pickup_address_json"]) if order["pickup_address_json"] else None,
                "carrier": order["carrier"], "trackingNumber": order["tracking_number"],
                "localDriver": bool(order["local_driver"]),
                "deliveryMessage": "A local driver is handling this delivery." if order["local_driver"] else None,
                "createdAt": order["created_at"], "updatedAt": order["updated_at"],
            })
    return {"marketId": market_id, "orders": result}


@router.get("/orders")
def buyer_order_history(buyer: Buyer) -> dict:
    """List only the authenticated buyer's market orders, newest first."""
    with transaction() as conn:
        orders = conn.execute(
            "SELECT o.*, m.name AS market_name FROM market_orders o JOIN markets m ON m.id = o.market_id "
            "WHERE o.buyer_account_id = ? ORDER BY o.created_at DESC", (buyer.id,)
        ).fetchall()
        result = []
        for order in orders:
            items = conn.execute(
                "SELECT product_name, price_cents, amount, quantity_value, quantity_unit "
                "FROM market_order_items WHERE order_id = ? ORDER BY id", (order["id"],)
            ).fetchall()
            result.append({
                "id": order["id"], "market": {"id": order["market_id"], "name": order["market_name"]},
                "items": [dict(item) for item in items], "totalCents": order["total_cents"],
                "fulfillmentMethod": order["fulfillment_method"], "status": order["fulfillment_status"],
                "createdAt": order["created_at"],
            })
    return {"orders": result}


@router.get("/orders/{order_id}")
def buyer_order_details(order_id: str, buyer: Buyer) -> dict:
    with transaction() as conn:
        order = conn.execute(
            "SELECT o.*, m.name AS market_name FROM market_orders o JOIN markets m ON m.id = o.market_id "
            "WHERE o.id = ? AND o.buyer_account_id = ?", (order_id, buyer.id)
        ).fetchone()
        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
        items = conn.execute(
            "SELECT product_name, price_cents, amount, quantity_value, quantity_unit "
            "FROM market_order_items WHERE order_id = ? ORDER BY id", (order_id,)
        ).fetchall()
    return {
        "id": order["id"], "market": {"id": order["market_id"], "name": order["market_name"]},
        "items": [dict(item) for item in items], "totalCents": order["total_cents"],
        "fulfillmentMethod": order["fulfillment_method"], "status": order["fulfillment_status"],
        "shippingAddress": json.loads(order["shipping_address_json"]) if order["shipping_address_json"] else None,
        "pickupAddress": json.loads(order["pickup_address_json"]) if order["pickup_address_json"] else None,
        "carrier": order["carrier"], "trackingNumber": order["tracking_number"],
        "localDriver": bool(order["local_driver"]),
        "deliveryMessage": "A local driver is handling this delivery." if order["local_driver"] else None,
        "createdAt": order["created_at"],
    }


@router.post("/orders/{order_id}/buy-again")
def buyer_buy_again(order_id: str, buyer: Buyer) -> dict:
    """Resolve a past order against current products without changing a cart or checkout."""
    with transaction() as conn:
        order = conn.execute("SELECT market_id FROM market_orders WHERE id = ? AND buyer_account_id = ?", (order_id, buyer.id)).fetchone()
        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
        snapshots = conn.execute("SELECT product_id, price_cents, amount FROM market_order_items WHERE order_id = ?", (order_id,)).fetchall()
        ids = [row["product_id"] for row in snapshots]
        if not ids:
            return {"items": [], "unavailable": [], "priceChanged": []}
        marks = ", ".join("?" for _ in ids)
        current = conn.execute(f"SELECT id, price_cents FROM market_products WHERE market_id = ? AND id IN ({marks})", (order["market_id"], *ids)).fetchall()
    products = {row["id"]: row for row in current}
    available = [row for row in snapshots if row["product_id"] in products]
    return {"items": [{"productId": row["product_id"], "quantity": row["amount"]} for row in available],
            "unavailable": [row["product_id"] for row in snapshots if row["product_id"] not in products],
            "priceChanged": [row["product_id"] for row in available if products[row["product_id"]]["price_cents"] != row["price_cents"]]}


@owner_router.patch("/{market_id}/orders/{order_id}/status")
def update_market_order_status(
    market_id: str, order_id: str, body: UpdateOrderStatus, owner: MarketOwner
) -> dict:
    """Move one owner-owned order through its fulfillment-specific state machine."""
    with transaction() as conn:
        order = conn.execute(
            "SELECT * FROM market_orders WHERE id = ? AND market_id = ? "
            "AND EXISTS (SELECT 1 FROM markets WHERE id = ? AND owner_account_id = ?)",
            (order_id, market_id, market_id, owner.id),
        ).fetchone()
        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
        allowed = _VALID_TRANSITIONS[order["fulfillment_status"]]
        if body.status not in allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid order status transition")
        expected_terminal = "SHIPPING" if order["fulfillment_method"] == "SHIP" else "READY_FOR_PICKUP"
        if body.status in {"SHIPPING", "READY_FOR_PICKUP"} and body.status != expected_terminal:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "status does not match fulfillment method")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute("UPDATE market_orders SET fulfillment_status = ?, updated_at = ? WHERE id = ?", (body.status, now, order_id))
    return {"id": order_id, "status": body.status}


@owner_router.patch("/{market_id}/orders/{order_id}/tracking")
def update_market_order_tracking(
    market_id: str, order_id: str, body: UpdateTracking, owner: MarketOwner
) -> dict:
    with transaction() as conn:
        order = conn.execute(
            "SELECT fulfillment_method FROM market_orders WHERE id = ? AND market_id = ? "
            "AND EXISTS (SELECT 1 FROM markets WHERE id = ? AND owner_account_id = ?)",
            (order_id, market_id, market_id, owner.id),
        ).fetchone()
        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
        if order["fulfillment_method"] != "SHIP":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "tracking is only available for shipping orders")
        conn.execute("UPDATE market_orders SET carrier = ?, tracking_number = ?, updated_at = ? WHERE id = ?", (body.carrier, body.trackingNumber.strip(), datetime.now(timezone.utc).isoformat(timespec="seconds"), order_id))
    return {"id": order_id, "carrier": body.carrier, "trackingNumber": body.trackingNumber.strip()}


@owner_router.patch("/{market_id}/orders/{order_id}/local-driver")
def set_local_driver_delivery(market_id: str, order_id: str, owner: MarketOwner) -> dict:
    with transaction() as conn:
        order = conn.execute(
            "SELECT fulfillment_method FROM market_orders WHERE id = ? AND market_id = ? "
            "AND EXISTS (SELECT 1 FROM markets WHERE id = ? AND owner_account_id = ?)",
            (order_id, market_id, market_id, owner.id),
        ).fetchone()
        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "order not found")
        if order["fulfillment_method"] != "SHIP":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "local driver is only available for shipping orders")
        conn.execute(
            "UPDATE market_orders SET local_driver = 1, carrier = NULL, tracking_number = NULL, updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), order_id),
        )
    return {"id": order_id, "localDriver": True, "deliveryMessage": "A local driver is handling this delivery."}
