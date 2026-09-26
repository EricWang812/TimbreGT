"""Feature 1: merchant-side market-owner account and session behavior."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from api.db import fetch_one, transaction
from api.main import app
from api.market_auth import Account, current_market_owner


def _credentials(email: str = "owner@example.com", password: str = "correct horse battery") -> dict:
    return {"email": email, "password": password}


def test_market_owner_can_register_and_read_session():
    with TestClient(app) as client:
        created = client.post("/market-auth/register", json=_credentials())
        current = client.get("/market-auth/me")

    assert created.status_code == 201
    assert created.json()["email"] == "owner@example.com"
    assert created.json()["role"] == "MARKET_OWNER"
    assert current.status_code == 200
    assert current.json() == created.json()
    assert "HttpOnly" in created.headers["set-cookie"]
    row = fetch_one("SELECT password_hash FROM accounts WHERE email = ?", ("owner@example.com",))
    assert row is not None
    assert "correct horse battery" not in row["password_hash"]


def test_duplicate_email_is_case_insensitive():
    with TestClient(app) as client:
        first = client.post("/market-auth/register", json=_credentials("Case@Example.com"))
        duplicate = client.post("/market-auth/register", json=_credentials("case@example.com"))
    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_login_rejects_invalid_password_without_creating_session():
    with TestClient(app) as client:
        client.post("/market-auth/register", json=_credentials("login@example.com"))
        client.cookies.clear()
        denied = client.post(
            "/market-auth/login", json=_credentials("login@example.com", "incorrect password")
        )
        current = client.get("/market-auth/me")
    assert denied.status_code == 401
    assert denied.json()["detail"] == "invalid email or password"
    assert current.status_code == 401


def test_login_rotates_to_a_working_session_and_logout_revokes_it():
    with TestClient(app) as client:
        client.post("/market-auth/register", json=_credentials("cycle@example.com"))
        client.cookies.clear()
        login = client.post("/market-auth/login", json=_credentials("cycle@example.com"))
        assert login.status_code == 200
        assert client.get("/market-auth/me").status_code == 200
        logout = client.post("/market-auth/logout")
        assert logout.status_code == 204
        assert client.get("/market-auth/me").status_code == 401


def test_expired_session_is_rejected_and_removed():
    with TestClient(app) as client:
        client.post("/market-auth/register", json=_credentials("expired@example.com"))
        account = fetch_one("SELECT id FROM accounts WHERE email = ?", ("expired@example.com",))
        assert account is not None
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with transaction() as conn:
            conn.execute("UPDATE market_sessions SET expires_at = ? WHERE account_id = ?", (expired, account["id"]))
        denied = client.get("/market-auth/me")
    assert denied.status_code == 401
    assert fetch_one("SELECT 1 FROM market_sessions WHERE account_id = ?", (account["id"],)) is None


def test_market_owner_dependency_protects_server_routes():
    probe = APIRouter()

    @probe.get("/_test/market-owner")
    def protected(owner: Account = Depends(current_market_owner)) -> dict:
        return {"owner_id": owner.id}

    app.include_router(probe)
    with TestClient(app) as client:
        assert client.get("/_test/market-owner").status_code == 401
        created = client.post("/market-auth/register", json=_credentials("protected@example.com"))
        allowed = client.get("/_test/market-owner")
    assert allowed.status_code == 200
    assert allowed.json() == {"owner_id": created.json()["id"]}


def test_registration_validation_rejects_bad_inputs():
    with TestClient(app) as client:
        bad_email = client.post("/market-auth/register", json=_credentials("not-an-email"))
        short_password = client.post(
            "/market-auth/register", json={"email": "new@example.com", "password": "too short"}
        )
    assert bad_email.status_code == 422
    assert short_password.status_code == 422
