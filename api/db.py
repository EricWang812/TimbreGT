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
CREATE TABLE IF NOT EXISTS products (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    brand         TEXT NOT NULL,
    size          TEXT NOT NULL,
    category      TEXT NOT NULL,
    price_cents   INTEGER NOT NULL CHECK (price_cents > 0),
    image_url     TEXT NOT NULL,
    image_credit  TEXT NOT NULL
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
