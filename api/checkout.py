"""Checkout: the merchant originates instruction_id and hands off to the issuer.

    POST /cart/quote         {items} -> priced cart; creates nothing
    POST /checkout/confirm   {items} -> priced cart + instruction_id + session_id
        The browser passes session_id to the issuer widget, which runs the
        challenge directly against the issuer (docs/DECISIONS.md ADR 2).
    POST /checkout/complete  {instruction_id} -> {verified, transaction_id}
        Exactly two keys, whatever happened at the issuer (§2.5).
    GET  /orders/{instruction_id} -> the order as the merchant knows it (receipt)
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api import issuer_client
from api.cart import CartError, price_cart
from api.config import BUYER_SESSION_COOKIE, FREE_SHIPPING_MIN_CENTS, MAX_CART_LINES, MAX_QUANTITY, MERCHANT_ID
from api.db import fetch_one, transaction
from api.fulfillment_selection import _market_and_options
from api.market_auth import current_account_for_role
from api.market_orders import _address_snapshot, materialize_market_order

log = logging.getLogger(__name__)
router = APIRouter()


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a client-supplied price is rejected, not ignored
    product_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=MAX_QUANTITY)


class CartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CartLine] = Field(min_length=1, max_length=MAX_CART_LINES)


class Fulfillment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["SHIP", "PICKUP"]
    shippingAddressId: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def address_matches_method(self):
        if (self.method == "SHIP") != (self.shippingAddressId is not None):
            raise ValueError("shippingAddressId is required for shipping and only valid for shipping")
        return self


class ConfirmRequest(CartRequest):
    # Only a signed-in buyer's cart of market products uses this; guests omit it.
    fulfillment: Fulfillment | None = None


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction_id: UUID


class ApprovalResult(BaseModel):
    """Non-negotiable §2.5: all the merchant knows, and all it tells the browser."""
    verified: bool
    transaction_id: str | None


def _price(body: CartRequest, pickup: bool = False) -> dict:
    try:
        priced = price_cart([(line.product_id, line.quantity) for line in body.items])
    except CartError as exc:
        raise HTTPException(400, str(exc)) from exc
    if pickup:  # nothing is shipped, so nothing is charged for shipping
        priced = {**priced, "total_cents": priced["total_cents"] - priced["shipping_cents"], "shipping_cents": 0}
    return priced


class QuoteRequest(CartRequest):
    fulfillmentMethod: Literal["SHIP", "PICKUP"] | None = None


@router.post("/cart/quote")
def quote(body: QuoteRequest) -> dict:
    # The drawer's free-delivery meter reads the threshold from here, so the
    # web app never keeps a second copy of FREE_SHIPPING_MIN_CENTS.
    return {**_price(body, pickup=body.fulfillmentMethod == "PICKUP"), "free_shipping_min_cents": FREE_SHIPPING_MIN_CENTS}


def _signed_in_buyer(session_token: str | None):
    """The buyer behind the session cookie, or None for a guest (guests can still buy)."""
    try:
        return current_account_for_role(session_token, "BUYER", "buyer login required")
    except HTTPException:
        return None


def _market_orders_for(buyer_id: str, priced: dict, fulfillment: Fulfillment | None) -> list[dict]:
    """One pending market order per market in a signed-in buyer's cart.

    Nothing here is an order yet: materialize_market_order turns these into
    market_orders only after the issuer verifies the payment. Validation runs
    before the issuer session exists, so a bad choice never opens a payment.
    """
    ids = [line["product_id"] for line in priced["lines"]]
    with transaction() as conn:
        products = {row["id"]: row for row in conn.execute(
            f"SELECT id, market_id, quantity_value, quantity_unit FROM market_products WHERE id IN ({', '.join('?' for _ in ids)})",
            ids).fetchall()}
        grouped: dict[str, list[dict]] = {}
        for line in priced["lines"]:
            product = products.get(line["product_id"])
            if product is None:
                continue  # a legacy catalog line belongs to no market
            grouped.setdefault(product["market_id"], []).append({
                "productId": line["product_id"], "productName": line["name"], "priceCents": line["unit_cents"],
                "amount": line["quantity"], "quantityValue": product["quantity_value"], "quantityUnit": product["quantity_unit"],
            })
        if not grouped:
            return []
        if fulfillment is None:
            raise HTTPException(422, "Choose shipping or pickup to check out.")
        shipping = None
        if fulfillment.method == "SHIP":
            address = conn.execute("SELECT * FROM buyer_addresses WHERE id = ? AND buyer_account_id = ?",
                                   (fulfillment.shippingAddressId, buyer_id)).fetchone()
            if address is None:
                raise HTTPException(422, "Choose one of your saved shipping addresses.")
            shipping = _address_snapshot(address)
        orders = []
        for market_id, lines in grouped.items():
            market, options = _market_and_options(conn, market_id)
            if fulfillment.method not in options.availableMethods:
                raise HTTPException(409, f"{market['name']} does not offer {'shipping' if fulfillment.method == 'SHIP' else 'pickup'}.")
            orders.append({"marketId": market_id, "lines": lines,
                           "subtotalCents": sum(l["priceCents"] * l["amount"] for l in lines),
                           "shipping": shipping,
                           "pickup": options.pickupAddress.model_dump() if fulfillment.method == "PICKUP" else None})
    # Tax and shipping are charged on the whole cart. Each market order carries
    # its share, so a buyer's orders add up to what the bank approved.
    extra = priced["total_cents"] - priced["subtotal_cents"]
    for order in orders:
        order["totalCents"] = order["subtotalCents"] + round(extra * order["subtotalCents"] / priced["subtotal_cents"]) if priced["subtotal_cents"] else order["subtotalCents"]
    if sum(o["subtotalCents"] for o in orders) == priced["subtotal_cents"]:
        orders[-1]["totalCents"] += priced["total_cents"] - sum(o["totalCents"] for o in orders)
    for order in orders:
        order["method"] = fulfillment.method
    return orders


@router.post("/checkout/confirm")
def confirm(
    body: ConfirmRequest,
    buyer_session: Annotated[str | None, Cookie(alias=BUYER_SESSION_COOKIE)] = None,
) -> dict:
    buyer = _signed_in_buyer(buyer_session)
    # Pickup waives shipping only for a signed-in buyer whose market orders record the pickup.
    priced = _price(body, pickup=bool(buyer) and body.fulfillment is not None and body.fulfillment.method == "PICKUP")
    market_orders = _market_orders_for(buyer.id, priced, body.fulfillment) if buyer else []
    if not market_orders and priced["shipping_cents"] == 0 and body.fulfillment is not None and body.fulfillment.method == "PICKUP":
        priced = _price(body)  # no market order carries the pickup, so the usual shipping applies
    instruction_id = str(uuid.uuid4())
    try:
        session_id = issuer_client.create_session(instruction_id, priced["total_cents"], MERCHANT_ID)
    except issuer_client.IssuerError as exc:
        log.exception("issuer session creation failed")
        raise HTTPException(502, "payment service unavailable") from exc

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with transaction() as conn:
        conn.execute(
            "INSERT INTO orders (instruction_id, items_json, subtotal_cents, tax_cents, shipping_cents,"
            " total_cents, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (instruction_id, json.dumps(priced["lines"]), priced["subtotal_cents"], priced["tax_cents"],
             priced["shipping_cents"], priced["total_cents"], now),
        )
        # Same authorization instruction as the receipt: one bank approval covers every market order.
        for order in market_orders:
            conn.execute(
                "INSERT INTO market_checkout_sessions (instruction_id, authorization_instruction_id, buyer_account_id,"
                " market_id, items_json, subtotal_cents, total_cents, fulfillment_method, shipping_address_json,"
                " pickup_address_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), instruction_id, buyer.id, order["marketId"], json.dumps(order["lines"]),
                 order["subtotalCents"], order["totalCents"], order["method"],
                 json.dumps(order["shipping"]) if order["shipping"] else None,
                 json.dumps(order["pickup"]) if order["pickup"] else None, now),
            )
    # savedToAccount tells the buyer's own page whether order history will show it.
    return {"instruction_id": instruction_id, "session_id": session_id, **priced,
            "savedToAccount": bool(market_orders)}


@router.post("/checkout/complete", response_model=ApprovalResult)
def complete(body: CompleteRequest) -> ApprovalResult:
    instruction_id = str(body.instruction_id)
    if (
        fetch_one("SELECT 1 FROM orders WHERE instruction_id = ?", (instruction_id,)) is None
        and fetch_one(
            "SELECT 1 FROM market_checkout_sessions WHERE authorization_instruction_id = ?", (instruction_id,)
        ) is None
    ):
        raise HTTPException(404, "unknown order")
    try:
        result = issuer_client.approve(instruction_id)
    except issuer_client.IssuerError as exc:
        log.exception("issuer approval lookup failed")
        raise HTTPException(502, "payment service unavailable") from exc

    if result["verified"]:
        # Only a verified result changes the order. An unverified one leaves it
        # pending: the shopper may still finish the challenge, or it expires.
        with transaction() as conn:
            conn.execute(
                "UPDATE orders SET status = 'approved', transaction_id = ?"
                " WHERE instruction_id = ? AND status = 'pending'",
                (result["transaction_id"], instruction_id),
            )
            materialize_market_order(conn, instruction_id, result["transaction_id"])
    return ApprovalResult(verified=result["verified"], transaction_id=result["transaction_id"])


@router.get("/orders/{instruction_id}")
def get_order(instruction_id: UUID) -> dict:
    row = fetch_one("SELECT * FROM orders WHERE instruction_id = ?", (str(instruction_id),))
    if row is None:
        raise HTTPException(404, "unknown order")
    order = dict(row)
    order["lines"] = json.loads(order.pop("items_json"))
    return order
