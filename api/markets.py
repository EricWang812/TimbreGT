"""Market creation owned by the authenticated merchant account."""
import re
import uuid
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from api.db import fetch_one, transaction
from api.market_auth import MarketOwner

router = APIRouter(prefix="/markets", tags=["markets"])
DEFAULT_PRIMARY_COLOR = "#126B5B"
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CreateMarket(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("market name is required")
        return name


class MarketBranding(BaseModel):
    id: str
    name: str
    primaryColor: str
    logoUrl: str | None
    logoPlaceholder: str
    createdAt: str


class Market(MarketBranding):
    ownerAccountId: str


class UpdateBranding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    primaryColor: str | None = None
    logoUrl: str | None = Field(default=None, max_length=2048)

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("market name cannot be null")
        return CreateMarket.normalized_name(value)

    @field_validator("primaryColor")
    @classmethod
    def valid_color(cls, value: str | None) -> str | None:
        if value is None or not _HEX_COLOR.fullmatch(value):
            raise ValueError("primaryColor must be a six-digit hex color")
        return value.upper()

    @field_validator("logoUrl")
    @classmethod
    def valid_logo_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        parsed = urlparse(value)
        if value.startswith("/") and not value.startswith("//"):
            return value
        if parsed.scheme == "https" and parsed.netloc:
            return value
        raise ValueError("logoUrl must be an HTTPS URL or root-relative static path")


class PickupAddress(BaseModel):
    model_config = ConfigDict(extra="forbid")
    addressLine1: str = Field(min_length=1, max_length=160)
    addressLine2: str | None = Field(default=None, max_length=160)
    city: str = Field(min_length=1, max_length=100)
    stateRegion: str = Field(min_length=1, max_length=100)
    postalCode: str = Field(min_length=1, max_length=32)
    country: str = Field(min_length=1, max_length=100)

    @field_validator("addressLine1", "city", "stateRegion", "postalCode", "country")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("pickup address field is required")
        return normalized

    @field_validator("addressLine2")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None


class UpdatePickupSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pickupEnabled: bool | None = None
    pickupAddress: PickupAddress | None = None


class PickupSettings(BaseModel):
    pickupEnabled: bool
    pickupAddress: PickupAddress | None


ShippingMethod = Literal["USPS", "UPS", "FEDEX", "LOCAL_DRIVER"]


class UpdateShippingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shippingEnabled: StrictBool | None = None
    supportedShippingMethods: list[ShippingMethod] | None = Field(default=None, max_length=4)

    @field_validator("supportedShippingMethods")
    @classmethod
    def unique_methods(cls, value: list[ShippingMethod] | None) -> list[ShippingMethod] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("shipping methods must be unique")
        return value


class ShippingSettings(BaseModel):
    shippingEnabled: bool
    supportedShippingMethods: list[ShippingMethod]


def _placeholder(name: str) -> str:
    words = [word for word in name.split() if word]
    return "".join(word[0].upper() for word in words[:2]) or "M"


def _market(row) -> Market:
    return Market(
        id=row["id"],
        name=row["name"],
        ownerAccountId=row["owner_account_id"],
        primaryColor=row["primary_color"],
        logoUrl=row["logo_url"],
        logoPlaceholder=_placeholder(row["name"]),
        createdAt=row["created_at"],
    )


def _branding(row) -> MarketBranding:
    return MarketBranding(
        id=row["id"],
        name=row["name"],
        primaryColor=row["primary_color"],
        logoUrl=row["logo_url"],
        logoPlaceholder=_placeholder(row["name"]),
        createdAt=row["created_at"],
    )


def _pickup_address(row) -> PickupAddress | None:
    if row is None:
        return None
    return PickupAddress(
        addressLine1=row["address_line_1"],
        addressLine2=row["address_line_2"],
        city=row["city"],
        stateRegion=row["state_region"],
        postalCode=row["postal_code"],
        country=row["country"],
    )


def _owned_market(conn, market_id: str, owner_id: str):
    row = conn.execute(
        "SELECT * FROM markets WHERE id = ? AND owner_account_id = ?", (market_id, owner_id)
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market not found")
    return row


@router.post("", response_model=Market, status_code=status.HTTP_201_CREATED)
def create_market(body: CreateMarket, owner: MarketOwner) -> Market:
    market = Market(
        id=str(uuid.uuid4()),
        name=body.name,
        ownerAccountId=owner.id,
        primaryColor=DEFAULT_PRIMARY_COLOR,
        logoUrl=None,
        logoPlaceholder=_placeholder(body.name),
        createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    with transaction() as conn:
        conn.execute(
            "INSERT INTO markets (id, name, owner_account_id, primary_color, logo_url, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                market.id,
                market.name,
                market.ownerAccountId,
                market.primaryColor,
                market.logoUrl,
                market.createdAt,
            ),
        )
    return market


@router.get("/{market_id}", response_model=MarketBranding)
def get_market(market_id: str) -> MarketBranding:
    row = fetch_one("SELECT * FROM markets WHERE id = ?", (market_id,))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market not found")
    return _branding(row)


@router.patch("/{market_id}/branding", response_model=Market)
def update_branding(market_id: str, body: UpdateBranding, owner: MarketOwner) -> Market:
    supplied = body.model_fields_set
    if not supplied:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide a branding field")

    assignments: list[str] = []
    values: list[str | None] = []
    for field, column in (
        ("name", "name"),
        ("primaryColor", "primary_color"),
        ("logoUrl", "logo_url"),
    ):
        if field in supplied:
            assignments.append(f"{column} = ?")
            values.append(getattr(body, field))

    with transaction() as conn:
        cursor = conn.execute(
            f"UPDATE markets SET {', '.join(assignments)}"
            " WHERE id = ? AND owner_account_id = ?",
            (*values, market_id, owner.id),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "market not found")
        row = conn.execute("SELECT * FROM markets WHERE id = ?", (market_id,)).fetchone()
    return _market(row)


@router.get("/{market_id}/pickup-settings", response_model=PickupSettings)
def get_pickup_settings(market_id: str, owner: MarketOwner) -> PickupSettings:
    with transaction() as conn:
        market = _owned_market(conn, market_id, owner.id)
        address = conn.execute(
            "SELECT * FROM market_pickup_addresses WHERE market_id = ?", (market_id,)
        ).fetchone()
    return PickupSettings(pickupEnabled=bool(market["pickup_enabled"]), pickupAddress=_pickup_address(address))


@router.patch("/{market_id}/pickup-settings", response_model=PickupSettings)
def update_pickup_settings(
    market_id: str, body: UpdatePickupSettings, owner: MarketOwner
) -> PickupSettings:
    supplied = body.model_fields_set
    if not supplied:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide a pickup setting")

    with transaction() as conn:
        market = _owned_market(conn, market_id, owner.id)
        existing_address = conn.execute(
            "SELECT * FROM market_pickup_addresses WHERE market_id = ?", (market_id,)
        ).fetchone()
        pickup_enabled = body.pickupEnabled if "pickupEnabled" in supplied else bool(market["pickup_enabled"])
        address_supplied = "pickupAddress" in supplied
        has_address = existing_address is not None
        if address_supplied:
            has_address = body.pickupAddress is not None
        if pickup_enabled and not has_address:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "pickup address is required when pickup is enabled",
            )

        if address_supplied and body.pickupAddress is not None:
            address = body.pickupAddress
            conn.execute(
                "INSERT INTO market_pickup_addresses "
                "(market_id, address_line_1, address_line_2, city, state_region, postal_code, country, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(market_id) DO UPDATE SET address_line_1 = excluded.address_line_1, "
                "address_line_2 = excluded.address_line_2, city = excluded.city, "
                "state_region = excluded.state_region, postal_code = excluded.postal_code, "
                "country = excluded.country, updated_at = excluded.updated_at",
                (
                    market_id,
                    address.addressLine1,
                    address.addressLine2,
                    address.city,
                    address.stateRegion,
                    address.postalCode,
                    address.country,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
        conn.execute("UPDATE markets SET pickup_enabled = ? WHERE id = ?", (int(pickup_enabled), market_id))
        if address_supplied and body.pickupAddress is None:
            conn.execute("DELETE FROM market_pickup_addresses WHERE market_id = ?", (market_id,))
        address = conn.execute(
            "SELECT * FROM market_pickup_addresses WHERE market_id = ?", (market_id,)
        ).fetchone()
    return PickupSettings(pickupEnabled=pickup_enabled, pickupAddress=_pickup_address(address))


@router.get("/{market_id}/shipping-settings", response_model=ShippingSettings)
def get_shipping_settings(market_id: str, owner: MarketOwner) -> ShippingSettings:
    with transaction() as conn:
        market = _owned_market(conn, market_id, owner.id)
        methods = conn.execute(
            "SELECT method FROM market_shipping_methods WHERE market_id = ? ORDER BY method", (market_id,)
        ).fetchall()
    return ShippingSettings(
        shippingEnabled=bool(market["shipping_enabled"]),
        supportedShippingMethods=[row["method"] for row in methods],
    )


@router.patch("/{market_id}/shipping-settings", response_model=ShippingSettings)
def update_shipping_settings(
    market_id: str, body: UpdateShippingSettings, owner: MarketOwner
) -> ShippingSettings:
    supplied = body.model_fields_set
    if not supplied:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide a shipping setting")

    with transaction() as conn:
        market = _owned_market(conn, market_id, owner.id)
        existing_methods = [
            row["method"]
            for row in conn.execute(
                "SELECT method FROM market_shipping_methods WHERE market_id = ?", (market_id,)
            ).fetchall()
        ]
        shipping_enabled = (
            body.shippingEnabled if "shippingEnabled" in supplied else bool(market["shipping_enabled"])
        )
        methods = (
            list(body.supportedShippingMethods)
            if "supportedShippingMethods" in supplied
            else existing_methods
        )
        if shipping_enabled and not methods:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "a shipping method is required when shipping is enabled",
            )

        methods_supplied = "supportedShippingMethods" in supplied
        if methods_supplied and bool(market["shipping_enabled"]):
            conn.execute("UPDATE markets SET shipping_enabled = 0 WHERE id = ?", (market_id,))
        if methods_supplied:
            conn.execute("DELETE FROM market_shipping_methods WHERE market_id = ?", (market_id,))
            conn.executemany(
                "INSERT INTO market_shipping_methods (market_id, method) VALUES (?, ?)",
                [(market_id, method) for method in methods],
            )
        conn.execute("UPDATE markets SET shipping_enabled = ? WHERE id = ?", (int(shipping_enabled), market_id))
        rows = conn.execute(
            "SELECT method FROM market_shipping_methods WHERE market_id = ? ORDER BY method", (market_id,)
        ).fetchall()
    return ShippingSettings(
        shippingEnabled=shipping_enabled,
        supportedShippingMethods=[row["method"] for row in rows],
    )
