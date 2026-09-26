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
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api import issuer_client
from api.cart import CartError, price_cart
from api.config import MAX_CART_LINES, MAX_QUANTITY, MERCHANT_ID
from api.db import fetch_one, transaction

log = logging.getLogger(__name__)
router = APIRouter()


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")  # a client-supplied price is rejected, not ignored
    product_id: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=1, le=MAX_QUANTITY)


class CartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CartLine] = Field(min_length=1, max_length=MAX_CART_LINES)


class CompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction_id: UUID


class ApprovalResult(BaseModel):
    """Non-negotiable §2.5: all the merchant knows, and all it tells the browser."""
    verified: bool
    transaction_id: str | None


def _price(body: CartRequest) -> dict:
    try:
        return price_cart([(line.product_id, line.quantity) for line in body.items])
    except CartError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/cart/quote")
def quote(body: CartRequest) -> dict:
    return _price(body)


@router.post("/checkout/confirm")
def confirm(body: CartRequest) -> dict:
    priced = _price(body)
    instruction_id = str(uuid.uuid4())
    try:
        session_id = issuer_client.create_session(instruction_id, priced["total_cents"], MERCHANT_ID)
    except issuer_client.IssuerError as exc:
        log.exception("issuer session creation failed")
        raise HTTPException(502, "payment service unavailable") from exc

    with transaction() as conn:
        conn.execute(
            "INSERT INTO orders (instruction_id, items_json, subtotal_cents, tax_cents, shipping_cents,"
            " total_cents, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
            (instruction_id, json.dumps(priced["lines"]), priced["subtotal_cents"], priced["tax_cents"],
             priced["shipping_cents"], priced["total_cents"],
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return {"instruction_id": instruction_id, "session_id": session_id, **priced}


@router.post("/checkout/complete", response_model=ApprovalResult)
def complete(body: CompleteRequest) -> ApprovalResult:
    instruction_id = str(body.instruction_id)
    if fetch_one("SELECT 1 FROM orders WHERE instruction_id = ?", (instruction_id,)) is None:
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
    return ApprovalResult(verified=result["verified"], transaction_id=result["transaction_id"])


@router.get("/orders/{instruction_id}")
def get_order(instruction_id: UUID) -> dict:
    row = fetch_one("SELECT * FROM orders WHERE instruction_id = ?", (str(instruction_id),))
    if row is None:
        raise HTTPException(404, "unknown order")
    order = dict(row)
    order["lines"] = json.loads(order.pop("items_json"))
    return order
