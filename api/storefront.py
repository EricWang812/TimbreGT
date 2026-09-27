"""Public database-backed storefront reads for owner-managed markets."""
from fastapi import APIRouter, HTTPException

from api.db import fetch_all, fetch_one
from api.market_units import normalize_quantity

router = APIRouter(prefix="/storefront", tags=["storefront"])


@router.get("/markets")
def storefront_markets() -> dict:
    rows = fetch_all(
        "SELECT m.id, m.name, m.description, m.primary_color, m.logo_url, COUNT(p.id) AS product_count "
        "FROM markets m LEFT JOIN market_products p ON p.market_id = m.id "
        # Best-stocked first: the default storefront is the fullest market, and an
        # empty new market never becomes a buyer's landing page.
        "GROUP BY m.id ORDER BY product_count DESC, m.name"
    )
    return {"markets": [{"id": row["id"], "name": row["name"], "description": row["description"],
                          "primaryColor": row["primary_color"], "logoUrl": row["logo_url"], "productCount": row["product_count"]} for row in rows]}


@router.get("/markets/{market_id}/products")
def storefront_products(market_id: str) -> dict:
    market = fetch_one("SELECT id, name, description, primary_color, logo_url FROM markets WHERE id = ?", (market_id,))
    if market is None:
        raise HTTPException(404, "market not found")
    rows = fetch_all("SELECT * FROM market_products WHERE market_id = ? ORDER BY category, name", (market_id,))
    products = []
    for row in rows:
        normalized = normalize_quantity(row["quantity_value"], row["quantity_unit"])
        products.append({"id": row["id"], "market": market_id, "marketName": market["name"], "name": row["name"], "brand": row["brand"] or "",
                         "category": row["category"] or "Other", "size": f"{row['quantity_value']:g} {row['quantity_unit']}" if row["quantity_value"] else "",  # "52 fl oz", never split across lines
                         "price_cents": row["price_cents"], "image_url": row["photo_url"], "image_credit": "",
                         "quantity": row["quantity_value"], "unit": row["quantity_unit"],
                         "normalizedQuantity": normalized.value if normalized else None,
                         "normalizedUnit": normalized.unit if normalized else None})
    return {"market": {"id": market["id"], "name": market["name"], "description": market["description"], "primaryColor": market["primary_color"], "logoUrl": market["logo_url"]}, "products": products}


from pydantic import BaseModel, Field
from api.catalog import get_products

class CartProductsRequest(BaseModel):
    productIds: list[str] = Field(max_length=100)

@router.post("/cart-products")
def cart_products(body: CartProductsRequest):
    # Public catalog metadata only. Cart pricing remains server-authoritative.
    if not body.productIds:
        return {"products": []}
    marks = ",".join("?" for _ in body.productIds)
    rows = fetch_all(f"SELECT DISTINCT market_id FROM market_products WHERE id IN ({marks})", tuple(body.productIds))
    wanted = set(body.productIds)
    products = [p for row in rows for p in storefront_products(row["market_id"])["products"] if p["id"] in wanted]
    found = {p["id"] for p in products}
    products.extend(dict(p) for p in get_products(list(wanted - found)).values())
    return {"products": products}
