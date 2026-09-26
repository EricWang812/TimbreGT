"""Product catalog. Read-only at runtime; rows come from scripts/seed_demo.py."""
import sqlite3

from fastapi import APIRouter

from api.config import FREE_SHIPPING_MIN_CENTS
from api.db import fetch_all

router = APIRouter()

PRODUCT_COLUMNS = "id, name, brand, size, category, price_cents, image_url, image_credit"


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
    return {"free_shipping_min_cents": FREE_SHIPPING_MIN_CENTS}


@router.get("/catalog")
def list_catalog() -> list[dict]:
    rows = fetch_all(f"SELECT {PRODUCT_COLUMNS} FROM products ORDER BY category, name")
    return [dict(r) for r in rows]
