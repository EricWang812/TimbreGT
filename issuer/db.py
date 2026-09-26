"""Issuer database: raw SQL on SQLite, one short-lived connection per operation.

A connection per call (instead of one shared connection) means FastAPI's
threadpool can never interleave two transactions on the same handle.
Writes use BEGIN IMMEDIATE so a lock conflict surfaces at the start of the
transaction, not halfway through it.

Non-negotiable §2.2: no column here may hold a PAN. payment_tokens stores an
opaque provider token and the last four digits only.
"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from issuer.config import DB_BUSY_TIMEOUT_S, ISSUER_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_tokens (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL REFERENCES users(id),
    token_value   TEXT NOT NULL,
    last_four     TEXT NOT NULL CHECK (length(last_four) = 4),
    nickname      TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    user_id         TEXT NOT NULL REFERENCES users(id),
    label           TEXT NOT NULL,
    centroid        BLOB NOT NULL,
    spread          REAL NOT NULL,
    cohesion        REAL NOT NULL,
    low_confidence  INTEGER NOT NULL DEFAULT 0 CHECK (low_confidence IN (0, 1)),
    n_samples       INTEGER NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, label)
);

CREATE TABLE IF NOT EXISTS enroll_labels (
    user_id     TEXT NOT NULL REFERENCES users(id),
    label       TEXT NOT NULL,
    rerecords   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (user_id, label)
);

CREATE TABLE IF NOT EXISTS enroll_samples (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL REFERENCES users(id),
    label       TEXT NOT NULL,
    waveform    BLOB NOT NULL,
    embedding   BLOB NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    instruction_id  TEXT NOT NULL UNIQUE,
    user_id         TEXT REFERENCES users(id),  -- NULL until the cardholder is identified in the issuer widget
    amount_cents    INTEGER NOT NULL CHECK (amount_cents > 0),
    merchant_id     TEXT NOT NULL,
    labels_json     TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    extensions      INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'verified', 'failed', 'expired')),
    method          TEXT CHECK (method IN ('voice', 'passkey', 'voice+passkey')),
    transaction_id  TEXT,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS verifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT REFERENCES sessions(id),
    user_id     TEXT NOT NULL REFERENCES users(id),
    label       TEXT NOT NULL,
    score       REAL NOT NULL,
    threshold   REAL NOT NULL,
    passed      INTEGER NOT NULL CHECK (passed IN (0, 1)),
    replay      INTEGER NOT NULL DEFAULT 0 CHECK (replay IN (0, 1)),
    drift       REAL,
    latency_ms  REAL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webauthn_challenges (
    key         TEXT PRIMARY KEY,          -- 'register:<user_id>' or 'session:<session_id>'
    challenge   BLOB NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS passkeys (
    credential_id  BLOB PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id),
    public_key     BLOB NOT NULL,
    sign_count     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(
        ISSUER_DB,
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
