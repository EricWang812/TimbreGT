"""Buyer accounts built on the existing merchant account and session tables."""
import sqlite3
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel

from api.config import BUYER_SESSION_COOKIE
from api.db import fetch_one, transaction
from api.market_auth import (
    Credentials,
    _hash_password,
    _normalize_email,
    _token_hash,
    _verify_password,
    current_account_for_role,
    start_session,
)

router = APIRouter(prefix="/buyer-auth", tags=["buyer authentication"])


class BuyerAccount(BaseModel):
    id: str
    email: str
    role: Literal["BUYER"]


def current_buyer(
    session_token: Annotated[str | None, Cookie(alias=BUYER_SESSION_COOKIE)] = None,
) -> BuyerAccount:
    account = current_account_for_role(session_token, "BUYER", "buyer login required")
    return BuyerAccount.model_validate(account.model_dump())


Buyer = Annotated[BuyerAccount, Depends(current_buyer)]


@router.post("/register", response_model=BuyerAccount, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response) -> BuyerAccount:
    email = _normalize_email(body.email)
    account_id = str(uuid.uuid4())
    try:
        with transaction() as conn:
            conn.execute(
                "INSERT INTO accounts (id, email, password_hash, role, created_at) "
                "VALUES (?, ?, ?, 'BUYER', datetime('now'))",
                (account_id, email, _hash_password(body.password)),
            )
    except sqlite3.IntegrityError as exc:
        if fetch_one("SELECT 1 FROM accounts WHERE email = ?", (email,)) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "account already exists") from exc
        raise
    start_session(response, account_id, BUYER_SESSION_COOKIE)
    return BuyerAccount(id=account_id, email=email, role="BUYER")


@router.post("/login", response_model=BuyerAccount)
def login(body: Credentials, response: Response) -> BuyerAccount:
    email = _normalize_email(body.email)
    row = fetch_one(
        "SELECT id, email, password_hash, role FROM accounts WHERE email = ? AND role = 'BUYER'",
        (email,),
    )
    if row is None or not _verify_password(body.password, row["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    start_session(response, row["id"], BUYER_SESSION_COOKIE)
    return BuyerAccount(id=row["id"], email=row["email"], role="BUYER")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session_token: Annotated[str | None, Cookie(alias=BUYER_SESSION_COOKIE)] = None,
) -> None:
    if session_token:
        with transaction() as conn:
            conn.execute("DELETE FROM market_sessions WHERE token_hash = ?", (_token_hash(session_token),))
    response.delete_cookie(BUYER_SESSION_COOKIE, path="/", samesite="lax")


@router.get("/me", response_model=BuyerAccount)
def me(buyer: Buyer) -> BuyerAccount:
    return buyer


@router.get("/session")
def session_status(
    session_token: Annotated[str | None, Cookie(alias=BUYER_SESSION_COOKIE)] = None,
) -> dict:
    """Public storefront-safe session probe. Protected routes still use Buyer."""
    try:
        account = current_account_for_role(session_token, "BUYER", "buyer login required")
    except HTTPException:
        return {"account": None}
    return {"account": BuyerAccount.model_validate(account.model_dump()).model_dump()}
