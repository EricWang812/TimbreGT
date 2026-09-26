"""Product catalog. Read-only at runtime; rows come from scripts/seed_demo.py."""
import sqlite3

from fastapi import APIRouter

from api.config import FREE_SHIPPING_MIN_CENTS, MERCHANT_ID
from api.db import fetch_all
from api.llm import words

router = APIRouter()

PRODUCT_COLUMNS = "id, name, brand, size, category, price_cents, image_url, image_credit, market"

# Request-local scope follows the selected storefront through every shopping stage.
from contextvars import ContextVar
from fastapi import Query, HTTPException
from api.db import fetch_one

selected_market = ContextVar("selected_market", default=None)

async def shopping_market(marketId: str | None = Query(default=None)):
    if marketId and fetch_one("SELECT id FROM markets WHERE id = ?", (marketId,)) is None:
        raise HTTPException(404, "market not found")
    token = selected_market.set(marketId)
    try:
        yield
    finally:
        selected_market.reset(token)


def market_records():
    return [dict(row) for row in fetch_all("SELECT id, name, description FROM markets ORDER BY name")]


def merchant_scope(requested: str) -> tuple[bool, str | None]:
    requested_words = words(requested)
    for market in market_records():
        if requested.strip().casefold() == market["id"].casefold() or requested_words == words(market["name"]):
            return True, market["id"]
    return (True, None) if requested.strip().casefold() == MERCHANT_ID.casefold() else (False, None)


def get_products(product_ids: list[str]) -> dict[str, sqlite3.Row]:
    if not product_ids:
        return {}
    placeholders = ", ".join("?" for _ in product_ids)
    rows = fetch_all(f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id IN ({placeholders})", tuple(product_ids))
    return {r["id"]: r for r in rows}


@router.get("/store")
def store_info() -> dict:
    """Public facts about the store for its own pages (the hero's delivery pill),
    so the web app never keeps a second copy of a merchant setting."""
    return {"free_shipping_min_cents": FREE_SHIPPING_MIN_CENTS, "markets": market_records()}


@router.get("/catalog")
def list_catalog() -> list[dict]:
    market_id = selected_market.get()
    rows = fetch_all(
        "SELECT p.*, m.name AS market_name FROM market_products p JOIN markets m ON m.id = p.market_id "
        + ("WHERE p.market_id = ? " if market_id else "") + "ORDER BY p.category, p.name",
        (market_id,) if market_id else (),
    )
    return [{"id": p["id"], "name": p["name"], "brand": p["brand"] or "",
             "size": f"{p['quantity_value']:g} {p['quantity_unit']}" if p["quantity_value"] else "",
             "category": p["category"] or "Other", "price_cents": p["price_cents"],
             "image_url": p["photo_url"] or "", "image_credit": "",
             "market": p["market_id"], "marketName": p["market_name"]} for p in rows]
