"""Merchant database: raw SQL on SQLite, one short-lived connection per operation.

Same connection discipline as issuer/db.py, deliberately duplicated rather
than shared: the two services must not share stateful modules (CLAUDE.md §5).
The merchant stores no token, no score, no cardholder identity, and nothing
about how a purchase was verified: an order knows only its transaction_id.
"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from api.config import DB_BUSY_TIMEOUT_S, MERCHANT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id             TEXT PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('MARKET_OWNER', 'BUYER')),
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_sessions (
    token_hash   TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    expires_at   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_market_sessions_account
    ON market_sessions(account_id);

CREATE TABLE IF NOT EXISTS buyer_addresses (
    id                TEXT PRIMARY KEY,
    buyer_account_id  TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    recipient_name    TEXT NOT NULL CHECK (length(trim(recipient_name)) > 0),
    address_line_1    TEXT NOT NULL CHECK (length(trim(address_line_1)) > 0),
    address_line_2    TEXT,
    city              TEXT NOT NULL CHECK (length(trim(city)) > 0),
    state_region      TEXT NOT NULL CHECK (length(trim(state_region)) > 0),
    postal_code       TEXT NOT NULL CHECK (length(trim(postal_code)) > 0),
    country           TEXT NOT NULL CHECK (length(trim(country)) > 0),
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_buyer_addresses_buyer
    ON buyer_addresses(buyer_account_id);

CREATE TRIGGER IF NOT EXISTS require_buyer_address_account
BEFORE INSERT ON buyer_addresses
WHEN NOT EXISTS (
    SELECT 1 FROM accounts
    WHERE id = NEW.buyer_account_id AND role = 'BUYER'
)
BEGIN
    SELECT RAISE(ABORT, 'buyer account required');
END;

CREATE TABLE IF NOT EXISTS buyer_market_fulfillment_selections (
    buyer_account_id    TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    market_id           TEXT NOT NULL REFERENCES markets(id) ON DELETE RESTRICT,
    fulfillment_method  TEXT NOT NULL CHECK (fulfillment_method IN ('SHIP', 'PICKUP')),
    shipping_address_id TEXT REFERENCES buyer_addresses(id) ON DELETE RESTRICT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (buyer_account_id, market_id),
    CHECK (
        (fulfillment_method = 'SHIP' AND shipping_address_id IS NOT NULL)
        OR (fulfillment_method = 'PICKUP' AND shipping_address_id IS NULL)
    )
);

CREATE TRIGGER IF NOT EXISTS require_buyer_fulfillment_selection_account
BEFORE INSERT ON buyer_market_fulfillment_selections
WHEN NOT EXISTS (
    SELECT 1 FROM accounts
    WHERE id = NEW.buyer_account_id AND role = 'BUYER'
)
BEGIN
    SELECT RAISE(ABORT, 'buyer account required');
END;

CREATE TRIGGER IF NOT EXISTS require_selection_address_belongs_to_buyer_insert
BEFORE INSERT ON buyer_market_fulfillment_selections
WHEN NEW.shipping_address_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM buyer_addresses
    WHERE id = NEW.shipping_address_id AND buyer_account_id = NEW.buyer_account_id
)
BEGIN
    SELECT RAISE(ABORT, 'shipping address must belong to buyer');
END;

CREATE TRIGGER IF NOT EXISTS require_selection_address_belongs_to_buyer_update
BEFORE UPDATE OF buyer_account_id, shipping_address_id ON buyer_market_fulfillment_selections
WHEN NEW.shipping_address_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM buyer_addresses
    WHERE id = NEW.shipping_address_id AND buyer_account_id = NEW.buyer_account_id
)
BEGIN
    SELECT RAISE(ABORT, 'shipping address must belong to buyer');
END;

CREATE TABLE IF NOT EXISTS markets (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL CHECK (length(trim(name)) > 0),
    owner_account_id  TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    primary_color     TEXT NOT NULL DEFAULT '#126B5B',
    logo_url          TEXT,
    pickup_enabled    INTEGER NOT NULL DEFAULT 0 CHECK (pickup_enabled IN (0, 1)),
    shipping_enabled  INTEGER NOT NULL DEFAULT 0 CHECK (shipping_enabled IN (0, 1)),
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_markets_owner
    ON markets(owner_account_id);

CREATE TABLE IF NOT EXISTS market_pickup_addresses (
    market_id       TEXT PRIMARY KEY REFERENCES markets(id) ON DELETE RESTRICT,
    address_line_1  TEXT NOT NULL CHECK (length(trim(address_line_1)) > 0),
    address_line_2  TEXT,
    city            TEXT NOT NULL CHECK (length(trim(city)) > 0),
    state_region    TEXT NOT NULL CHECK (length(trim(state_region)) > 0),
    postal_code     TEXT NOT NULL CHECK (length(trim(postal_code)) > 0),
    country         TEXT NOT NULL CHECK (length(trim(country)) > 0),
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_shipping_methods (
    market_id  TEXT NOT NULL REFERENCES markets(id) ON DELETE RESTRICT,
    method     TEXT NOT NULL CHECK (method IN ('USPS', 'UPS', 'FEDEX', 'LOCAL_DRIVER')),
    PRIMARY KEY (market_id, method)
);

CREATE TRIGGER IF NOT EXISTS require_market_owner_account
BEFORE INSERT ON markets
WHEN NOT EXISTS (
    SELECT 1 FROM accounts
    WHERE id = NEW.owner_account_id AND role = 'MARKET_OWNER'
)
BEGIN
    SELECT RAISE(ABORT, 'market owner account required');
END;

CREATE TABLE IF NOT EXISTS market_products (
    id              TEXT PRIMARY KEY,
    market_id       TEXT NOT NULL REFERENCES markets(id) ON DELETE RESTRICT,
    name            TEXT NOT NULL CHECK (length(trim(name)) > 0),
    price_cents     INTEGER NOT NULL CHECK (price_cents >= 0),
    photo_url       TEXT,
    quantity_value  REAL,
    quantity_unit   TEXT,
    created_at      TEXT NOT NULL,
    CHECK (
        (quantity_value IS NULL AND quantity_unit IS NULL)
        OR (
            quantity_value IS NOT NULL
            AND quantity_value > 0
            AND quantity_unit IN ('mg', 'g', 'kg', 'oz', 'lb', 'mL', 'L', 'fl oz', 'gal', 'count')
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_market_products_market
    ON market_products(market_id);

CREATE TABLE IF NOT EXISTS market_checkout_sessions (
    instruction_id          TEXT PRIMARY KEY,
    authorization_instruction_id TEXT NOT NULL,
    buyer_account_id        TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    market_id               TEXT NOT NULL REFERENCES markets(id) ON DELETE RESTRICT,
    items_json              TEXT NOT NULL,
    subtotal_cents          INTEGER NOT NULL CHECK (subtotal_cents >= 0),
    total_cents             INTEGER NOT NULL CHECK (total_cents >= 0),
    fulfillment_method      TEXT NOT NULL CHECK (fulfillment_method IN ('SHIP', 'PICKUP')),
    shipping_address_json   TEXT,
    pickup_address_json     TEXT,
    created_at              TEXT NOT NULL,
    CHECK (
        (fulfillment_method = 'SHIP' AND shipping_address_json IS NOT NULL AND pickup_address_json IS NULL)
        OR (fulfillment_method = 'PICKUP' AND shipping_address_json IS NULL AND pickup_address_json IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_market_checkout_sessions_buyer
    ON market_checkout_sessions(buyer_account_id);

CREATE INDEX IF NOT EXISTS idx_market_checkout_sessions_authorization
    ON market_checkout_sessions(authorization_instruction_id);

CREATE TABLE IF NOT EXISTS market_orders (
    id                      TEXT PRIMARY KEY,
    instruction_id          TEXT NOT NULL UNIQUE REFERENCES market_checkout_sessions(instruction_id) ON DELETE RESTRICT,
    buyer_account_id        TEXT NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    market_id               TEXT NOT NULL REFERENCES markets(id) ON DELETE RESTRICT,
    subtotal_cents          INTEGER NOT NULL CHECK (subtotal_cents >= 0),
    total_cents             INTEGER NOT NULL CHECK (total_cents >= 0),
    fulfillment_method      TEXT NOT NULL CHECK (fulfillment_method IN ('SHIP', 'PICKUP')),
    status                  TEXT NOT NULL CHECK (status = 'NOT_STARTED'),
    fulfillment_status      TEXT NOT NULL DEFAULT 'NOT_STARTED' CHECK (fulfillment_status IN ('NOT_STARTED', 'FULFILLING', 'ORDER_COMPLETE', 'SHIPPING', 'READY_FOR_PICKUP')),
    carrier                 TEXT CHECK (carrier IN ('USPS', 'UPS', 'FEDEX')),
    tracking_number         TEXT,
    local_driver            INTEGER NOT NULL DEFAULT 0 CHECK (local_driver IN (0, 1)),
    transaction_id          TEXT NOT NULL,
    shipping_address_json   TEXT,
    pickup_address_json     TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    CHECK (
        (fulfillment_method = 'SHIP' AND shipping_address_json IS NOT NULL AND pickup_address_json IS NULL)
        OR (fulfillment_method = 'PICKUP' AND shipping_address_json IS NULL AND pickup_address_json IS NOT NULL)
    )
    , CHECK ((carrier IS NULL AND tracking_number IS NULL) OR (carrier IS NOT NULL AND tracking_number IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_market_orders_market
    ON market_orders(market_id);

CREATE INDEX IF NOT EXISTS idx_market_orders_buyer
    ON market_orders(buyer_account_id);

CREATE TABLE IF NOT EXISTS market_order_items (
    id                  TEXT PRIMARY KEY,
    order_id            TEXT NOT NULL REFERENCES market_orders(id) ON DELETE RESTRICT,
    product_id          TEXT NOT NULL,
    product_name        TEXT NOT NULL,
    price_cents         INTEGER NOT NULL CHECK (price_cents >= 0),
    amount              INTEGER NOT NULL CHECK (amount > 0),
    quantity_value      REAL,
    quantity_unit       TEXT,
    CHECK ((quantity_value IS NULL AND quantity_unit IS NULL) OR (quantity_value IS NOT NULL AND quantity_unit IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_market_order_items_order
    ON market_order_items(order_id);

CREATE TABLE IF NOT EXISTS products (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    brand         TEXT NOT NULL,
    size          TEXT NOT NULL,
    category      TEXT NOT NULL,
    price_cents   INTEGER NOT NULL CHECK (price_cents > 0),
    image_url     TEXT NOT NULL,
    image_credit  TEXT NOT NULL,
    market        TEXT NOT NULL DEFAULT 'grocer'   -- which boardwalk shop (api/catalog.py MARKETS)
);

CREATE TABLE IF NOT EXISTS orders (
    instruction_id  TEXT PRIMARY KEY,
    items_json      TEXT NOT NULL,
    subtotal_cents  INTEGER NOT NULL,
    tax_cents       INTEGER NOT NULL,
    shipping_cents  INTEGER NOT NULL,
    total_cents     INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'declined')),
    transaction_id  TEXT,
    created_at      TEXT NOT NULL
);

"""

QUANTITY_VALIDATION_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS validate_market_product_quantity_insert
BEFORE INSERT ON market_products
WHEN (NEW.quantity_value IS NULL AND NEW.quantity_unit IS NOT NULL)
  OR (NEW.quantity_value IS NOT NULL AND NEW.quantity_unit IS NULL)
  OR (NEW.quantity_value IS NOT NULL AND NEW.quantity_value <= 0)
  OR (NEW.quantity_unit IS NOT NULL AND NEW.quantity_unit NOT IN ('mg', 'g', 'kg', 'oz', 'lb', 'mL', 'L', 'fl oz', 'gal', 'count'))
BEGIN
    SELECT RAISE(ABORT, 'quantity and canonical unit must be provided together');
END;

CREATE TRIGGER IF NOT EXISTS validate_market_product_quantity_update
BEFORE UPDATE OF quantity_value, quantity_unit ON market_products
WHEN (NEW.quantity_value IS NULL AND NEW.quantity_unit IS NOT NULL)
  OR (NEW.quantity_value IS NOT NULL AND NEW.quantity_unit IS NULL)
  OR (NEW.quantity_value IS NOT NULL AND NEW.quantity_value <= 0)
  OR (NEW.quantity_unit IS NOT NULL AND NEW.quantity_unit NOT IN ('mg', 'g', 'kg', 'oz', 'lb', 'mL', 'L', 'fl oz', 'gal', 'count'))
BEGIN
    SELECT RAISE(ABORT, 'quantity and canonical unit must be provided together');
END;

"""

PICKUP_VALIDATION_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS prevent_market_create_with_pickup_enabled
BEFORE INSERT ON markets
WHEN NEW.pickup_enabled = 1
BEGIN
    SELECT RAISE(ABORT, 'pickup address required before enabling pickup');
END;

CREATE TRIGGER IF NOT EXISTS require_pickup_address_when_enabling
BEFORE UPDATE OF pickup_enabled ON markets
WHEN NEW.pickup_enabled = 1 AND NOT EXISTS (
    SELECT 1 FROM market_pickup_addresses WHERE market_id = NEW.id
)
BEGIN
    SELECT RAISE(ABORT, 'pickup address required before enabling pickup');
END;

CREATE TRIGGER IF NOT EXISTS prevent_pickup_address_removal_while_enabled
BEFORE DELETE ON market_pickup_addresses
WHEN (SELECT pickup_enabled FROM markets WHERE id = OLD.market_id) = 1
BEGIN
    SELECT RAISE(ABORT, 'disable pickup before removing pickup address');
END;
"""

SHIPPING_VALIDATION_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS prevent_market_create_with_shipping_enabled
BEFORE INSERT ON markets
WHEN NEW.shipping_enabled = 1
BEGIN
    SELECT RAISE(ABORT, 'shipping method required before enabling shipping');
END;

CREATE TRIGGER IF NOT EXISTS require_shipping_method_when_enabling
BEFORE UPDATE OF shipping_enabled ON markets
WHEN NEW.shipping_enabled = 1 AND NOT EXISTS (
    SELECT 1 FROM market_shipping_methods WHERE market_id = NEW.id
)
BEGIN
    SELECT RAISE(ABORT, 'shipping method required before enabling shipping');
END;

CREATE TRIGGER IF NOT EXISTS prevent_last_shipping_method_removal_while_enabled
BEFORE DELETE ON market_shipping_methods
WHEN (SELECT shipping_enabled FROM markets WHERE id = OLD.market_id) = 1
  AND NOT EXISTS (
      SELECT 1 FROM market_shipping_methods
      WHERE market_id = OLD.market_id AND method != OLD.method
  )
BEGIN
    SELECT RAISE(ABORT, 'disable shipping before removing the last shipping method');
END;
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        MERCHANT_DB,
        timeout=DB_BUSY_TIMEOUT_S,
        check_same_thread=False,
        isolation_level=None,  # autocommit; transactions are explicit below
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = _connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        # Additive migration: catalogs seeded before the boardwalk shops were
        # all grocery, which is what the default says.
        if "market" not in {row["name"] for row in conn.execute("PRAGMA table_info(products)")}:
            conn.execute("ALTER TABLE products ADD COLUMN market TEXT NOT NULL DEFAULT 'grocer'")
        # Additive migration for databases created by Feature 2. SQLite's
        # CREATE TABLE IF NOT EXISTS does not add later branding columns.
        market_columns = {row["name"] for row in conn.execute("PRAGMA table_info(markets)")}
        if "primary_color" not in market_columns:
            conn.execute("ALTER TABLE markets ADD COLUMN primary_color TEXT NOT NULL DEFAULT '#126B5B'")
        if "logo_url" not in market_columns:
            conn.execute("ALTER TABLE markets ADD COLUMN logo_url TEXT")
        if "pickup_enabled" not in market_columns:
            conn.execute("ALTER TABLE markets ADD COLUMN pickup_enabled INTEGER NOT NULL DEFAULT 0")
        if "shipping_enabled" not in market_columns:
            conn.execute("ALTER TABLE markets ADD COLUMN shipping_enabled INTEGER NOT NULL DEFAULT 0")
        # Additive migration for Feature 4/5 seller-product databases. The
        # validation triggers installed below also protect these SQLite tables,
        # whose existing constraints cannot be altered in place.
        product_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(market_products)")
        }
        if "quantity_value" not in product_columns:
            conn.execute("ALTER TABLE market_products ADD COLUMN quantity_value REAL")
        if "quantity_unit" not in product_columns:
            conn.execute("ALTER TABLE market_products ADD COLUMN quantity_unit TEXT")
        checkout_columns = {row["name"] for row in conn.execute("PRAGMA table_info(market_checkout_sessions)")}
        if "authorization_instruction_id" not in checkout_columns:
            conn.execute("ALTER TABLE market_checkout_sessions ADD COLUMN authorization_instruction_id TEXT")
            conn.execute(
                "UPDATE market_checkout_sessions SET authorization_instruction_id = instruction_id "
                "WHERE authorization_instruction_id IS NULL"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_market_checkout_sessions_authorization "
            "ON market_checkout_sessions(authorization_instruction_id)"
        )
        order_columns = {row["name"] for row in conn.execute("PRAGMA table_info(market_orders)")}
        if "fulfillment_status" not in order_columns:
            conn.execute("ALTER TABLE market_orders ADD COLUMN fulfillment_status TEXT NOT NULL DEFAULT 'NOT_STARTED'")
        if "carrier" not in order_columns:
            conn.execute("ALTER TABLE market_orders ADD COLUMN carrier TEXT")
        if "tracking_number" not in order_columns:
            conn.execute("ALTER TABLE market_orders ADD COLUMN tracking_number TEXT")
        if "local_driver" not in order_columns:
            conn.execute("ALTER TABLE market_orders ADD COLUMN local_driver INTEGER NOT NULL DEFAULT 0")
        conn.executescript(QUANTITY_VALIDATION_TRIGGERS)
        conn.executescript(PICKUP_VALIDATION_TRIGGERS)
        conn.executescript(SHIPPING_VALIDATION_TRIGGERS)
    finally:
        conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = _connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def fetch_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    conn = _connect()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()
