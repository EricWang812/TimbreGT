"""Product catalog. Read-only at runtime; rows come from scripts/seed_demo.py."""
import sqlite3

from fastapi import APIRouter

from api.config import FREE_SHIPPING_MIN_CENTS, MERCHANT_ID
from api.db import fetch_all
from api.llm import words

router = APIRouter()

PRODUCT_COLUMNS = "id, name, brand, size, category, price_cents, image_url, image_credit, market"

# The boardwalk: several themed shops, one merchant. They share one catalog,
# one cart, and one checkout, so the issuer boundary is unchanged; the shop is
# only a label on each product. Order is the order they appear on the page.
# "aliases" are plain words a shopper might use for the shop ("the pet store").
MARKETS = [
    {"id": "grocer", "name": "Seaside Grocer", "tagline": "Fresh from the coast, and the pantry behind it.",
     "aliases": "grocery groceries food supermarket"},
    {"id": "tech", "name": "Seaside Tech", "tagline": "Headphones, speakers, and power for the boardwalk.",
     "aliases": "electronics electronic gadgets"},
    {"id": "sun", "name": "Sandbar Sun & Care", "tagline": "Sunscreen, lip balm, and after-beach care.",
     "aliases": "beauty pharmacy drugstore sunscreen skincare"},
    {"id": "pets", "name": "Landlubber Pets", "tagline": "For friends with four legs and no sea legs.",
     "aliases": "pet dog cat"},
]
MARKET_IDS = {m["id"] for m in MARKETS}
_SHARED_SHOP_WORDS = words("Seaside Market store shop and")


def merchant_scope(requested: str) -> tuple[bool, str | None]:
    """(sold here, shop). A named boardwalk shop ("Seaside Tech", "the pet
    shop") limits a search to it; the merchant itself means every shop."""
    requested_words = words(requested)
    if not requested_words:
        return False, None
    for shop in MARKETS:
        if requested_words & (words(f"{shop['name']} {shop['aliases']}") - _SHARED_SHOP_WORDS):
            return True, shop["id"]
    merchant_words = words(f"{MERCHANT_ID} Seaside Market")
    if requested_words <= merchant_words or merchant_words <= requested_words:
        return True, None
    return False, None


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
    return {"free_shipping_min_cents": FREE_SHIPPING_MIN_CENTS, "markets": MARKETS}


@router.get("/catalog")
def list_catalog() -> list[dict]:
    rows = fetch_all(f"SELECT {PRODUCT_COLUMNS} FROM products ORDER BY category, name")
    return [dict(r) for r in rows]
