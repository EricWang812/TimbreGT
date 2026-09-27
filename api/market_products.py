"""Creation of products owned by an authenticated owner's market.

The existing ``products`` table remains the seeded Seaside demo catalog. Its
required merchandising fields do not match seller-created products, so this
additive table preserves that working path until a later catalog adapter joins
the two sources.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.db import transaction
from api.market_auth import MarketOwner
from api.market_units import NormalizedUnit, ProductUnit, UnitDimension, normalize_quantity

router = APIRouter(prefix="/markets", tags=["market products"])


def _optional_label(value: str | None) -> str | None:
    """Brand and category are optional labels: trimmed, and blank means none."""
    if value is None:
        return None
    return " ".join(value.split()) or None


class CreateProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    photoUrl: str | None = Field(default=None, max_length=2048)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)
    unit: ProductUnit | None = None
    brand: str | None = Field(default=None, max_length=80)
    # The storefront groups products into sections by category.
    category: str | None = Field(default=None, max_length=60)

    @field_validator("brand")
    @classmethod
    def normalized_brand(cls, value: str | None) -> str | None:
        return _optional_label(value)

    @field_validator("category")
    @classmethod
    def normalized_category(cls, value: str | None) -> str | None:
        label = _optional_label(value)
        return label.lower() if label else None  # "Dairy" joins the existing "dairy" section

    @field_validator("name")
    @classmethod
    def normalized_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("product name is required")
        return name

    @field_validator("price", mode="before")
    @classmethod
    def numeric_price(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError("price must be numeric")
        return value

    @field_validator("quantity", mode="before")
    @classmethod
    def numeric_quantity(cls, value):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            raise ValueError("quantity must be numeric")
        return value

    @field_validator("photoUrl")
    @classmethod
    def valid_photo_url(cls, value: str | None) -> str | None:
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
        raise ValueError("photoUrl must be an HTTPS URL or root-relative static path")

    @model_validator(mode="after")
    def complete_measurement(self):
        if (self.quantity is None) != (self.unit is None):
            raise ValueError("quantity and unit must be provided together")
        return self


class Product(BaseModel):
    id: str
    marketId: str
    name: str
    price: float
    priceCents: int
    photoUrl: str | None
    brand: str | None = None
    category: str | None = None
    quantity: float | None
    unit: ProductUnit | None
    quantityPerDollar: float | None
    normalizedQuantity: float | None
    normalizedUnit: NormalizedUnit | None
    quantityDimension: UnitDimension | None
    normalizedQuantityPerDollar: float | None
    createdAt: str


class UpdateProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    price: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    photoUrl: str | None = Field(default=None, max_length=2048)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=4)
    unit: ProductUnit | None = None
    brand: str | None = Field(default=None, max_length=80)
    category: str | None = Field(default=None, max_length=60)

    @field_validator("brand")
    @classmethod
    def normalized_optional_brand(cls, value: str | None) -> str | None:
        return _optional_label(value)

    @field_validator("category")
    @classmethod
    def normalized_optional_category(cls, value: str | None) -> str | None:
        label = _optional_label(value)
        return label.lower() if label else None

    @field_validator("name")
    @classmethod
    def normalized_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("product name cannot be null")
        return CreateProduct.normalized_name(value)

    @field_validator("price", mode="before")
    @classmethod
    def numeric_optional_price(cls, value):
        if value is None:
            raise ValueError("price cannot be null")
        return CreateProduct.numeric_price(value)

    @field_validator("quantity", mode="before")
    @classmethod
    def numeric_optional_quantity(cls, value):
        return CreateProduct.numeric_quantity(value)

    @field_validator("photoUrl")
    @classmethod
    def valid_optional_photo_url(cls, value: str | None) -> str | None:
        return CreateProduct.valid_photo_url(value)


def _product(row) -> Product:
    derived = _derived_quantity_fields(row["quantity_value"], row["quantity_unit"], row["price_cents"])
    return Product(
        id=row["id"],
        marketId=row["market_id"],
        name=row["name"],
        price=row["price_cents"] / 100,
        priceCents=row["price_cents"],
        photoUrl=row["photo_url"],
        brand=row["brand"],
        category=row["category"],
        quantity=row["quantity_value"],
        unit=row["quantity_unit"],
        **derived,
        createdAt=row["created_at"],
    )


def _quantity_per_dollar(quantity: float | None, price_cents: int) -> float | None:
    """Return the declared product unit amount per USD without persisting it.

    The display unit remains on ``Product.unit``. It is intentionally not
    normalized here: Feature 8 will compare compatible units only.
    """
    if quantity is None or price_cents <= 0:
        return None
    return float(Decimal(str(quantity)) * 100 / Decimal(price_cents))


def _derived_quantity_fields(
    quantity: float | None, unit: ProductUnit | None, price_cents: int
) -> dict[str, float | str | None]:
    normalized = normalize_quantity(quantity, unit)
    if normalized is None:
        return {
            "quantityPerDollar": None,
            "normalizedQuantity": None,
            "normalizedUnit": None,
            "quantityDimension": None,
            "normalizedQuantityPerDollar": None,
        }
    return {
        "quantityPerDollar": _quantity_per_dollar(quantity, price_cents),
        "normalizedQuantity": normalized.value,
        "normalizedUnit": normalized.unit,
        "quantityDimension": normalized.dimension,
        "normalizedQuantityPerDollar": _quantity_per_dollar(normalized.value, price_cents),
    }


def _owned_market(conn, market_id: str, owner_id: str) -> None:
    if conn.execute(
        "SELECT 1 FROM markets WHERE id = ? AND owner_account_id = ?",
        (market_id, owner_id),
    ).fetchone() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "market not found")


@router.post("/{market_id}/products", response_model=Product, status_code=status.HTTP_201_CREATED)
def create_product(market_id: str, body: CreateProduct, owner: MarketOwner) -> Product:
    quantity = float(body.quantity) if body.quantity is not None else None
    price_cents = int(body.price * 100)
    product = Product(
        id=str(uuid.uuid4()),
        marketId=market_id,
        name=body.name,
        price=float(body.price),
        priceCents=price_cents,
        photoUrl=body.photoUrl,
        brand=body.brand,
        category=body.category,
        quantity=quantity,
        unit=body.unit,
        **_derived_quantity_fields(quantity, body.unit, price_cents),
        createdAt=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    with transaction() as conn:
        _owned_market(conn, market_id, owner.id)
        conn.execute(
            "INSERT INTO market_products "
            "(id, market_id, name, price_cents, photo_url, brand, category, quantity_value, quantity_unit, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                product.id,
                product.marketId,
                product.name,
                product.priceCents,
                product.photoUrl,
                product.brand,
                product.category,
                product.quantity,
                product.unit,
                product.createdAt,
            ),
        )
    return product


@router.get("/{market_id}/products", response_model=list[Product])
def list_products(market_id: str, owner: MarketOwner) -> list[Product]:
    with transaction() as conn:
        _owned_market(conn, market_id, owner.id)
        rows = conn.execute(
            "SELECT * FROM market_products WHERE market_id = ? ORDER BY created_at, id",
            (market_id,),
        ).fetchall()
    return [_product(row) for row in rows]


@router.patch("/{market_id}/products/{product_id}", response_model=Product)
def update_product(
    market_id: str, product_id: str, body: UpdateProduct, owner: MarketOwner
) -> Product:
    supplied = body.model_fields_set
    if not supplied:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "provide a product field")

    with transaction() as conn:
        _owned_market(conn, market_id, owner.id)
        current = conn.execute(
            "SELECT * FROM market_products WHERE id = ? AND market_id = ?", (product_id, market_id)
        ).fetchone()
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")

        quantity = body.quantity if "quantity" in supplied else current["quantity_value"]
        unit = body.unit if "unit" in supplied else current["quantity_unit"]
        if (quantity is None) != (unit is None):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "quantity and unit must be provided together",
            )

        assignments: list[str] = []
        values: list[str | int | float | None] = []
        if "name" in supplied:
            assignments.append("name = ?")
            values.append(body.name)
        if "price" in supplied:
            assignments.append("price_cents = ?")
            values.append(int(body.price * 100))
        if "photoUrl" in supplied:
            assignments.append("photo_url = ?")
            values.append(body.photoUrl)
        for field in ("brand", "category"):
            if field in supplied:
                assignments.append(f"{field} = ?")
                values.append(getattr(body, field))
        if "quantity" in supplied:
            assignments.append("quantity_value = ?")
            values.append(float(body.quantity) if body.quantity is not None else None)
        if "unit" in supplied:
            assignments.append("quantity_unit = ?")
            values.append(body.unit)
        cursor = conn.execute(
            f"UPDATE market_products SET {', '.join(assignments)}"
            " WHERE id = ? AND market_id = ?",
            (*values, product_id, market_id),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
        row = conn.execute("SELECT * FROM market_products WHERE id = ?", (product_id,)).fetchone()
    return _product(row)


@router.delete("/{market_id}/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(market_id: str, product_id: str, owner: MarketOwner) -> None:
    with transaction() as conn:
        _owned_market(conn, market_id, owner.id)
        cursor = conn.execute(
            "DELETE FROM market_products WHERE id = ? AND market_id = ?",
            (product_id, market_id),
        )
        if cursor.rowcount != 1:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "product not found")
