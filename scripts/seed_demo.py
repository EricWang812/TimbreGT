"""Seed the demo: the Seaside Market catalog and the demo cardholders.

Usage: python -m scripts.seed_demo   (normally via `make seed` or `make reset`)

Idempotent: products are upserted, cardholders are created once, and each
cardholder gets a payment token only if they have none.

Catalog: real products from Open Food Facts (names and sizes as printed on
the package; photos in web/public/products/, CC BY-SA 3.0, Open Food Facts
contributors). Prices are approximate US retail, set by hand for the demo.

Cardholders are fictional. Their cards are tokenized through the configured
PaymentProvider from a named sandbox test token (Stripe's `pm_card_*`), never
from a card number (non-negotiable §2.2).
"""
import dataclasses
import json
from datetime import datetime, timezone

from api import db as merchant_db
from issuer import db as issuer_db
from issuer.config import STRIPE_SECRET_KEY
from issuer.payments import get_provider
from ml.constants import REPO_ROOT

CATALOG_FILE = REPO_ROOT / "scripts" / "seed_catalog.json"
IMAGE_DIR = REPO_ROOT / "web" / "public" / "products"
IMAGE_CREDIT = "Photo: Open Food Facts contributors, CC BY-SA 3.0"
FAKE_TOKEN_PREFIX = "fake_tok_"   # tokens minted by issuer/payments/fake_provider.py

DEMO_CARDHOLDERS = [
    {"id": "maya", "display_name": "Maya Torres", "test_token": "pm_card_visa", "nickname": "Everyday Visa"},
    {"id": "jordan", "display_name": "Jordan Lee", "test_token": "pm_card_mastercard", "nickname": "Travel Mastercard"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seed_catalog() -> int:
    products = json.loads(CATALOG_FILE.read_text("utf-8"))
    missing = [p["barcode"] for p in products if not (IMAGE_DIR / f"{p['barcode']}.jpg").exists()]
    if missing:
        raise FileNotFoundError(f"product photos missing in {IMAGE_DIR}: {missing}")
    with merchant_db.transaction() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO products"
            " (id, name, brand, size, category, price_cents, image_url, image_credit)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(p["id"], p["name"], p["brand"], p["size"], p["category"], p["price_cents"],
              f"/products/{p['barcode']}.jpg", IMAGE_CREDIT) for p in products],
        )
    return len(products)


def seed_cardholders() -> list[str]:
    provider = get_provider()
    created = []
    for holder in DEMO_CARDHOLDERS:
        with issuer_db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
                         (holder["id"], holder["display_name"], _now()))
        existing = issuer_db.fetch_one("SELECT id, token_value FROM payment_tokens WHERE user_id = ?",
                                       (holder["id"],))
        # A fake-provider token is replaced once a Stripe key is configured, in
        # place, so voice enrollments and passkeys are kept (no `make reset`).
        stale = existing is not None and STRIPE_SECRET_KEY and existing["token_value"].startswith(FAKE_TOKEN_PREFIX)
        if existing is not None and not stale:
            continue
        # Tokenize outside any transaction: with Stripe this is a network call.
        token = dataclasses.replace(provider.create_token(holder["id"], holder["test_token"]),
                                    nickname=holder["nickname"])
        with issuer_db.transaction() as conn:
            if stale:
                conn.execute("UPDATE payment_tokens SET token_value = ?, last_four = ?, nickname = ? WHERE id = ?",
                             (token.value, token.last_four, token.nickname, existing["id"]))
            else:
                conn.execute(
                    "INSERT INTO payment_tokens (user_id, token_value, last_four, nickname, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (holder["id"], token.value, token.last_four, token.nickname, _now()),
                )
        verb = "re-tokenized with Stripe" if stale else "created"
        created.append(f"{holder['display_name']} ({token.nickname} ending {token.last_four}, {verb})")
    return created


def main() -> None:
    merchant_db.init_db()
    issuer_db.init_db()
    print(f"catalog: {seed_catalog()} products")
    created = seed_cardholders()
    print("cardholders: " + (", ".join(created) if created else "already seeded"))


if __name__ == "__main__":
    main()
