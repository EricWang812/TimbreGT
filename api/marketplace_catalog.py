"""Read-only marketplace catalog adapter for agentic shopping.

It never changes inventory, carts, orders, fulfillment, or payment state.
"""
from fastapi import APIRouter, Query

from api.db import fetch_all
from api.market_units import normalize_quantity

router = APIRouter(prefix="/agentic-shopping/commerce", tags=["agentic marketplace"])


@router.get("/marketplace-products")
def search_marketplace_products(
    query: str = Query(min_length=1, max_length=160),
    unit: str | None = Query(default=None, max_length=16),
) -> dict:
    """Search live market products and retain dimensions for safe comparison."""
    terms = [term for term in query.lower().split() if term]
    if not terms:
        return {"products": []}
    rows = fetch_all(
        "SELECT p.*, m.name AS market_name FROM market_products p JOIN markets m ON m.id = p.market_id "
        "WHERE " + " AND ".join("lower(p.name) LIKE ?" for _ in terms) + " ORDER BY p.price_cents, p.id",
        tuple(f"%{term}%" for term in terms),
    )
    products = []
    for row in rows:
        normalized = normalize_quantity(row["quantity_value"], row["quantity_unit"])
        if unit and (normalized is None or row["quantity_unit"] != unit):
            continue
        normalized_per_dollar = (
            normalized.value * 100 / row["price_cents"]
            if normalized is not None and row["price_cents"] > 0 else None
        )
        products.append({
            "id": row["id"], "marketId": row["market_id"], "marketName": row["market_name"],
            "name": row["name"], "priceCents": row["price_cents"], "quantity": row["quantity_value"],
            "unit": row["quantity_unit"], "quantityPerDollar": (
                row["quantity_value"] * 100 / row["price_cents"]
                if row["quantity_value"] is not None and row["price_cents"] > 0 else None
            ),
            "normalizedQuantity": normalized.value if normalized else None,
            "normalizedUnit": normalized.unit if normalized else None,
            "quantityDimension": normalized.dimension if normalized else None,
            "normalizedQuantityPerDollar": normalized_per_dollar,
        })
    return {"products": products}
