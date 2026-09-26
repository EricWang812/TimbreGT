"""Buyer fulfillment selection, kept separate from the existing payment checkout."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.buyer_auth import Buyer
from api.markets import PickupAddress
from api.db import transaction

router = APIRouter(prefix="/buyer/markets", tags=["buyer fulfillment"])

FulfillmentMethod = Literal["SHIP", "PICKUP"]


class FulfillmentOptions(BaseModel):
    marketId: str
    availableMethods: list[FulfillmentMethod]
    supportedShippingMethods: list[str]
    pickupAddress: PickupAddress | None


class SelectFulfillment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fulfillmentMethod: FulfillmentMethod
    shippingAddressId: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def address_matches_method(self):
        if self.fulfillmentMethod == "SHIP" and self.shippingAddressId is None:
            raise ValueError("shippingAddressId is required for shipping")
        if self.fulfillmentMethod == "PICKUP" and self.shippingAddressId is not None:
            raise ValueError("shippingAddressId is only valid for shipping")
        return self


class FulfillmentSelection(BaseModel):
    marketId: str
    fulfillmentMethod: FulfillmentMethod
    shippingAddressId: str | None
    pickupAddress: PickupAddress | None


def _market_and_options(conn, market_id: str) -> tuple[object, FulfillmentOptions]:
    market = conn.execute("SELECT * FROM markets WHERE id = ?", (market_id,)).fetchone()
    if market is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market not found")
    shipping_methods = [
        row["method"]
        for row in conn.execute(
            "SELECT method FROM market_shipping_methods WHERE market_id = ? ORDER BY method", (market_id,)
        ).fetchall()
    ]
    pickup_row = conn.execute(
        "SELECT * FROM market_pickup_addresses WHERE market_id = ?", (market_id,)
    ).fetchone()
    pickup_address = (
        PickupAddress(
            addressLine1=pickup_row["address_line_1"],
            addressLine2=pickup_row["address_line_2"],
            city=pickup_row["city"],
            stateRegion=pickup_row["state_region"],
            postalCode=pickup_row["postal_code"],
            country=pickup_row["country"],
        )
        if pickup_row is not None and bool(market["pickup_enabled"])
        else None
    )
    available: list[FulfillmentMethod] = []
    if bool(market["shipping_enabled"]) and shipping_methods:
        available.append("SHIP")
    if pickup_address is not None:
        available.append("PICKUP")
    return market, FulfillmentOptions(
        marketId=market_id,
        availableMethods=available,
        supportedShippingMethods=shipping_methods if "SHIP" in available else [],
        pickupAddress=pickup_address,
    )


@router.get("/{market_id}/fulfillment-options", response_model=FulfillmentOptions)
def fulfillment_options(market_id: str, buyer: Buyer) -> FulfillmentOptions:
    with transaction() as conn:
        _, options = _market_and_options(conn, market_id)
    return options


@router.put("/{market_id}/fulfillment-selection", response_model=FulfillmentSelection)
def select_fulfillment(
    market_id: str, body: SelectFulfillment, buyer: Buyer
) -> FulfillmentSelection:
    with transaction() as conn:
        _, options = _market_and_options(conn, market_id)
        if body.fulfillmentMethod not in options.availableMethods:
            raise HTTPException(status.HTTP_409_CONFLICT, "selected fulfillment method is unavailable")
        if body.fulfillmentMethod == "SHIP":
            address = conn.execute(
                "SELECT 1 FROM buyer_addresses WHERE id = ? AND buyer_account_id = ?",
                (body.shippingAddressId, buyer.id),
            ).fetchone()
            if address is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "shipping address not found")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO buyer_market_fulfillment_selections "
            "(buyer_account_id, market_id, fulfillment_method, shipping_address_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(buyer_account_id, market_id) DO UPDATE SET "
            "fulfillment_method = excluded.fulfillment_method, "
            "shipping_address_id = excluded.shipping_address_id, updated_at = excluded.updated_at",
            (buyer.id, market_id, body.fulfillmentMethod, body.shippingAddressId, now, now),
        )
    return FulfillmentSelection(
        marketId=market_id,
        fulfillmentMethod=body.fulfillmentMethod,
        shippingAddressId=body.shippingAddressId,
        pickupAddress=options.pickupAddress if body.fulfillmentMethod == "PICKUP" else None,
    )
