"""Merchant-side account sessions for market owners.

This identity belongs to the marketplace administration surface. It stays
separate from issuer/cardholder identity and from Timbre purchase approval.
"""
import hashlib
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from api.config import (
    MARKET_SESSION_COOKIE,
    MARKET_SESSION_COOKIE_SECURE,
    MARKET_SESSION_TTL_SECONDS,
)
from api.db import fetch_one, transaction

router = APIRouter(prefix="/market-auth", tags=["market authentication"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)


class Account(BaseModel):
    id: str
    email: str
    role: Literal["MARKET_OWNER", "BUYER"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not _EMAIL_RE.fullmatch(normalized):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid email address")
    return normalized


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return secrets.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _account(row) -> Account:
    return Account(id=row["id"], email=row["email"], role=row["role"])


def start_session(response: Response, account_id: str, cookie_name: str = MARKET_SESSION_COOKIE) -> None:
    token = secrets.token_urlsafe(32)
    now = _now()
    expires = now + timedelta(seconds=MARKET_SESSION_TTL_SECONDS)
    with transaction() as conn:
        conn.execute("DELETE FROM market_sessions WHERE expires_at <= ?", (now.isoformat(),))
        conn.execute(
            "INSERT INTO market_sessions (token_hash, account_id, expires_at, created_at)"
            " VALUES (?, ?, ?, ?)",
            (_token_hash(token), account_id, expires.isoformat(), now.isoformat()),
        )
    response.set_cookie(
        cookie_name,
        token,
        max_age=MARKET_SESSION_TTL_SECONDS,
        httponly=True,
        secure=MARKET_SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def current_account_for_role(session_token: str | None, role: str, required_message: str) -> Account:
    if not session_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, required_message)
    row = fetch_one(
        "SELECT a.id, a.email, a.role, s.expires_at FROM market_sessions s"
        " JOIN accounts a ON a.id = s.account_id"
        " WHERE s.token_hash = ? AND a.role = ?",
        (_token_hash(session_token), role),
    )
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, required_message)
    if datetime.fromisoformat(row["expires_at"]) <= _now():
        with transaction() as conn:
            conn.execute("DELETE FROM market_sessions WHERE token_hash = ?", (_token_hash(session_token),))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"{role.lower().replace('_', ' ')} session expired")
    return _account(row)


def current_market_owner(
    session_token: Annotated[str | None, Cookie(alias=MARKET_SESSION_COOKIE)] = None,
) -> Account:
    return current_account_for_role(session_token, "MARKET_OWNER", "market owner login required")


MarketOwner = Annotated[Account, Depends(current_market_owner)]


@router.post("/register", response_model=Account, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response) -> Account:
    email = _normalize_email(body.email)
    account_id = str(uuid.uuid4())
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO accounts (id, email, password_hash, role, created_at)"
                " VALUES (?, ?, ?, 'MARKET_OWNER', ?)",
                (account_id, email, _hash_password(body.password), _now().isoformat()),
            )
    except sqlite3.IntegrityError as exc:
        # Keep the public error stable without exposing database details.
        if fetch_one("SELECT 1 FROM accounts WHERE email = ?", (email,)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "account already exists") from exc
        raise
    start_session(response, account_id)
    return Account(id=account_id, email=email, role="MARKET_OWNER")


@router.post("/login", response_model=Account)
def login(body: Credentials, response: Response) -> Account:
    email = _normalize_email(body.email)
    row = fetch_one(
        "SELECT id, email, password_hash, role FROM accounts WHERE email = ? AND role = 'MARKET_OWNER'",
        (email,),
    )
    if row is None or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    start_session(response, row["id"])
    return _account(row)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: Annotated[str | None, Cookie(alias=MARKET_SESSION_COOKIE)] = None,
) -> None:
    if session_token:
        with transaction() as conn:
            conn.execute("DELETE FROM market_sessions WHERE token_hash = ?", (_token_hash(session_token),))
    response.delete_cookie(MARKET_SESSION_COOKIE, path="/", samesite="lax")


@router.get("/me", response_model=Account)
def me(owner: MarketOwner) -> Account:
    return owner


@router.get("/session")
def session_status(
    session_token: Annotated[str | None, Cookie(alias=MARKET_SESSION_COOKIE)] = None,
) -> dict:
    """Public storefront-safe session probe. Owner routes remain protected."""
    try:
        account = current_account_for_role(session_token, "MARKET_OWNER", "market owner login required")
    except HTTPException:
        return {"account": None}
    return {"account": account.model_dump()}
