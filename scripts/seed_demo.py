"""Seed the demo: the Seaside Market catalog and the demo cardholders.

Usage: python -m scripts.seed_demo   (normally via `make seed` or `make reset`)

Idempotent: products are upserted, cardholders are created once, and each
cardholder gets a payment token only if they have none.

Catalog: real products from the Open Food Facts projects (Food, Beauty, Pet
Food, and Products Facts; names and sizes as printed on the package; photos in
web/public/products/, CC BY-SA 3.0, each project's contributors), sold across
the boardwalk shops in api/catalog.py MARKETS. Prices are approximate US
retail, set by hand for the demo.

Cardholders are fictional. Their cards are tokenized through the configured
PaymentProvider from a named sandbox test token (Stripe's `pm_card_*`), never
from a card number (non-negotiable §2.2).
"""
import dataclasses
import json
import uuid
from datetime import datetime, timezone

from api import db as merchant_db
MARKET_IDS = {"grocer", "tech", "sun", "pets"}  # seed input validation only
from api.market_auth import _hash_password
from issuer import db as issuer_db
from issuer.config import CYBERSOURCE_CUSTOMER_TOKENS
from issuer.payments import active_provider_name, get_provider, token_is_current
from ml.constants import REPO_ROOT

CATALOG_FILE = REPO_ROOT / "scripts" / "seed_catalog.json"
IMAGE_DIR = REPO_ROOT / "web" / "public" / "products"
# A product's "photo" key names its source; food is the default. All four are
# Open Food Facts projects under the same license.
IMAGE_CREDITS = {
    "food": "Photo: Open Food Facts contributors, CC BY-SA 3.0",
    "beauty": "Photo: Open Beauty Facts contributors, CC BY-SA 3.0",
    "petfood": "Photo: Open Pet Food Facts contributors, CC BY-SA 3.0",
    "products": "Photo: Open Products Facts contributors, CC BY-SA 3.0",
}
DEFAULT_MARKET = "grocer"   # a product without a "market" key is sold by Seaside Grocer
SEASIDE_OWNER_ID = "00000000-0000-4000-8000-000000000001"
SEASIDE_MARKET_ID = "00000000-0000-4000-8000-000000000002"
SEASIDE_PRODUCTS = [
    ("Wild Planet", "Albacore Tuna", 449, 5, "oz", "seafood", "wild-planet-albacore"),
    ("Kirkland Signature", "Wild Argentine Red Shrimp", 2199, 2, "lb", "seafood", "kirkland-red-shrimp"),
    ("Dole", "Organic Bananas", 299, 3, "lb", "produce", None),
    ("Dave's Killer Bread", "21 Whole Grains and Seeds Bread", 699, 27, "oz", "bakery", "daves-21-grains"),
    ("Chobani", "Greek Yogurt, Nonfat Plain", 649, 32, "oz", "dairy", None),
    ("Cabot Creamery", "Seriously Sharp Cheddar", 429, 8, "oz", "dairy", "cabot-seriously-sharp"),
    ("Fage", "Total 0% Greek Yogurt", 749, 32, "oz", "dairy", "fage-total-0"),
    ("Tajín", "Clásico Seasoning, Reduced Sodium", 349, 5, "oz", "pantry", "tajin-reduced-sodium"),
    ("Jif", "Creamy Peanut Butter", 349, 16, "oz", "pantry", "jif-creamy"),
    ("Terra Delyssa", "Extra Virgin Olive Oil", 1199, 750, "mL", "pantry", None),
    ("Quaker", "Old Fashioned Oats", 649, 42, "oz", "pantry", "quaker-old-fashioned"),
    ("Huy Fong Foods", "Sriracha Hot Chili Sauce", 499, 17, "oz", "pantry", "huy-fong-sriracha"),
    ("Pirate's Booty", "Aged White Cheddar Puffs", 399, 4, "oz", "snacks", "pirates-booty"),
    ("Simple Mills", "Almond Flour Crackers, Farmhouse Cheddar", 499, 4.25, "oz", "snacks", "simple-mills-cheddar"),
    ("GoGo SqueeZ", "AppleApple Fruit Pouch", 149, 3.2, "oz", "snacks", None),
    ("Café Bustelo", "Espresso Ground Coffee", 599, 10, "oz", "drinks", None),
    ("Simply Orange", "Pulp Free Orange Juice", 549, 52, "fl oz", "drinks", "simply-orange"),
    ("S.Pellegrino", "Sparkling Natural Mineral Water", 249, 750, "mL", "drinks", None),
]

# "test_token" is a Stripe named test PaymentMethod (also understood by the
# fake provider). With PAYMENT_PROVIDER=visa the card is instead the
# cardholder's CyberSource customer token from .env. The shown nickname is the
# label plus the card brand the provider reports ("Everyday Visa").
DEMO_CARDHOLDERS = [
    {"id": "maya", "display_name": "Maya Torres", "test_token": "pm_card_visa", "label": "Everyday"},
    {"id": "jordan", "display_name": "Jordan Lee", "test_token": "pm_card_mastercard", "label": "Travel"},
]


def _card_reference(holder: dict) -> str:
    if active_provider_name() != "visa":
        return holder["test_token"]
    reference = CYBERSOURCE_CUSTOMER_TOKENS.get(holder["id"], "")
    if not reference:
        raise RuntimeError(f"PAYMENT_PROVIDER=visa: set CYBERSOURCE_CUSTOMER_{holder['id'].upper()} in .env "
                           "to the customer token ID from the CyberSource Business Center")
    return reference


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seed_catalog() -> int:
    products = json.loads(CATALOG_FILE.read_text("utf-8"))
    missing = [p["barcode"] for p in products if not (IMAGE_DIR / f"{p['barcode']}.jpg").exists()]
    if missing:
        raise FileNotFoundError(f"product photos missing in {IMAGE_DIR}: {missing}")
    unknown = {p.get("market", DEFAULT_MARKET) for p in products} - MARKET_IDS
    if unknown:
        raise ValueError(f"products name shops that do not exist: {sorted(unknown)}")
    with merchant_db.transaction() as conn:
        # The JSON is the whole catalog: drop products it no longer lists, so a
        # re-seed never shows a removed item with a missing photo. Orders keep
        # their own copy of each line (items_json), so nothing else refers here.
        ids = [p["id"] for p in products]
        conn.execute(f"DELETE FROM products WHERE id NOT IN ({', '.join('?' for _ in ids)})", ids)
        conn.executemany(
            "INSERT OR REPLACE INTO products"
            " (id, name, brand, size, category, price_cents, image_url, image_credit, market)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(p["id"], p["name"], p["brand"], p["size"], p["category"], p["price_cents"],
              f"/products/{p['barcode']}.jpg", IMAGE_CREDITS[p.get("photo", "food")],
              p.get("market", DEFAULT_MARKET)) for p in products],
        )
    return len(products)


def seed_seaside_marketplace() -> int:
    """Seed the original storefront as an ordinary persisted owner market."""
    with merchant_db.transaction() as conn:
        conn.execute("INSERT OR IGNORE INTO accounts (id, email, password_hash, role, created_at) VALUES (?, ?, ?, 'MARKET_OWNER', ?)",
                     (SEASIDE_OWNER_ID, "seaside-system@timbre.local", _hash_password("seaside-system-owner"), _now()))
        conn.execute("INSERT OR IGNORE INTO markets (id, name, owner_account_id, primary_color, description, created_at) VALUES (?, 'Seaside Grocer', ?, '#126B5B', 'Fresh from the coast, and the pantry behind it.', ?)",
                     (SEASIDE_MARKET_ID, SEASIDE_OWNER_ID, _now()))
        for brand, name, cents, quantity, unit, category, legacy_id in SEASIDE_PRODUCTS:
            photo = None
            if legacy_id:
                legacy = conn.execute("SELECT image_url FROM products WHERE id = ?", (legacy_id,)).fetchone()
                photo = legacy["image_url"] if legacy else None
            conn.execute("INSERT OR REPLACE INTO market_products (id, market_id, name, brand, category, price_cents, photo_url, quantity_value, quantity_unit, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (str(uuid.uuid5(uuid.NAMESPACE_URL, f"timbre:seaside:{name}")), SEASIDE_MARKET_ID, name, brand, category, cents, photo, quantity, unit, _now()))
    return len(SEASIDE_PRODUCTS)


def seed_cardholders() -> list[str]:
    provider = get_provider()
    created = []
    for holder in DEMO_CARDHOLDERS:
        with issuer_db.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
                         (holder["id"], holder["display_name"], _now()))
        existing = issuer_db.fetch_one("SELECT id, token_value FROM payment_tokens WHERE user_id = ?",
                                       (holder["id"],))
        # A card tokenized by a different provider (switching Stripe, Visa, or
        # the offline fake) is replaced in place, so voice enrollments and
        # passkeys are kept (no `make reset`).
        stale = existing is not None and not token_is_current(existing["token_value"])
        if existing is not None and not stale:
            continue
        # Tokenize outside any transaction: with Stripe or Visa this is a network call.
        token = provider.create_token(holder["id"], _card_reference(holder))
        token = dataclasses.replace(token, nickname=f"{holder['label']} {token.nickname}")
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
        verb = f"re-tokenized with {active_provider_name()}" if stale else "created"
        created.append(f"{holder['display_name']} ({token.nickname} ending {token.last_four}, {verb})")
    return created


def main() -> None:
    merchant_db.init_db()
    issuer_db.init_db()
    print(f"catalog: {seed_catalog()} products")
    print(f"marketplace Seaside Grocer: {seed_seaside_marketplace()} products")
    created = seed_cardholders()
    print("cardholders: " + (", ".join(created) if created else "already seeded"))


if __name__ == "__main__":
    main()
