"""Private shipping addresses for authenticated buyer accounts."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.buyer_auth import Buyer
from api.db import transaction

router = APIRouter(prefix="/buyer/addresses", tags=["buyer addresses"])


class AddressInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipientName: str = Field(min_length=1, max_length=160)
    addressLine1: str = Field(min_length=1, max_length=160)
    addressLine2: str | None = Field(default=None, max_length=160)
    city: str = Field(min_length=1, max_length=100)
    stateRegion: str = Field(min_length=1, max_length=100)
    postalCode: str = Field(min_length=1, max_length=32)
    country: str = Field(min_length=1, max_length=100)

    @field_validator("recipientName", "addressLine1", "city", "stateRegion", "postalCode", "country")
    @classmethod
    def required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("address field is required")
        return normalized

    @field_validator("addressLine2")
    @classmethod
    def optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split()) or None


class BuyerAddress(AddressInput):
    id: str
    createdAt: str


def _address(row) -> BuyerAddress:
    return BuyerAddress(
        id=row["id"],
        recipientName=row["recipient_name"],
        addressLine1=row["address_line_1"],
        addressLine2=row["address_line_2"],
        city=row["city"],
        stateRegion=row["state_region"],
        postalCode=row["postal_code"],
        country=row["country"],
        createdAt=row["created_at"],
    )


@router.post("", response_model=BuyerAddress, status_code=status.HTTP_201_CREATED)
def create_address(body: AddressInput, buyer: Buyer) -> BuyerAddress:
    address = BuyerAddress(
        id=str(uuid.uuid4()),
        createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **body.model_dump(),
    )
    with transaction() as conn:
        conn.execute(
            "INSERT INTO buyer_addresses "
            "(id, buyer_account_id, recipient_name, address_line_1, address_line_2, city, "
            "state_region, postal_code, country, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                address.id,
                buyer.id,
                address.recipientName,
                address.addressLine1,
                address.addressLine2,
                address.city,
                address.stateRegion,
                address.postalCode,
                address.country,
                address.createdAt,
            ),
        )
    return address


@router.get("", response_model=list[BuyerAddress])
def list_addresses(buyer: Buyer) -> list[BuyerAddress]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM buyer_addresses WHERE buyer_account_id = ? ORDER BY created_at, id",
            (buyer.id,),
        ).fetchall()
    return [_address(row) for row in rows]
