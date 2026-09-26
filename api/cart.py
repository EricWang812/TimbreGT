"""Server-side cart pricing. The cart itself lives in the browser; prices never
do. Every amount here comes from the catalog, so a client cannot change what
it pays. All arithmetic is in integer cents."""
from api.catalog import get_products
from api.db import fetch_all
from api.config import FREE_SHIPPING_MIN_CENTS, SHIPPING_CENTS, TAX_RATE_BPS

BPS_DENOMINATOR = 10_000


class CartError(ValueError):
    """The cart cannot be priced as submitted (unknown or duplicate product)."""


def tax_for(subtotal_cents: int) -> int:
    # Round half up, in integers: no float ever touches money.
    return (subtotal_cents * TAX_RATE_BPS + BPS_DENOMINATOR // 2) // BPS_DENOMINATOR


def shipping_for(subtotal_cents: int) -> int:
    return 0 if subtotal_cents >= FREE_SHIPPING_MIN_CENTS else SHIPPING_CENTS


def price_cart(lines: list[tuple[str, int]]) -> dict:
    """lines: (product_id, quantity) pairs, quantities already range-checked."""
    ids = [product_id for product_id, _ in lines]
    if len(set(ids)) != len(ids):
        raise CartError("each product may appear only once; combine quantities")
    products = get_products(ids)
    # Storefront marketplace products are additive. Resolve any ID missing
    # from the legacy catalog from the persisted seller catalog so the
    # existing browser cart and issuer checkout remain usable during migration.
    missing = [product_id for product_id in ids if product_id not in products]
    if missing:
        marks = ", ".join("?" for _ in missing)
        products.update({row["id"]: row for row in fetch_all(
            f"SELECT id, name, price_cents FROM market_products WHERE id IN ({marks})", tuple(missing)
        )})
    unknown = [pid for pid in ids if pid not in products]
    if unknown:
        raise CartError(f"unknown product ids: {unknown}")

    priced = []
    for product_id, quantity in lines:
        p = products[product_id]
        priced.append({
            "product_id": product_id,
            "name": p["name"],
            "unit_cents": p["price_cents"],
            "quantity": quantity,
            "line_cents": p["price_cents"] * quantity,
        })
    subtotal = sum(line["line_cents"] for line in priced)
    tax = tax_for(subtotal)
    shipping = shipping_for(subtotal)
    return {
        "lines": priced,
        "subtotal_cents": subtotal,
        "tax_cents": tax,
        "shipping_cents": shipping,
        "total_cents": subtotal + tax + shipping,
    }
