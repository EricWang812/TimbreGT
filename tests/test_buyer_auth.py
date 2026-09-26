"""Feature 9: buyer accounts reuse merchant account session infrastructure."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from api.buyer_auth import BuyerAccount, current_buyer
from api.db import fetch_one, transaction
from api.main import app


def _credentials(email: str = "buyer@example.com", password: str = "correct horse battery") -> dict:
    return {"email": email, "password": password}


def test_buyer_can_register_and_read_their_session():
    with TestClient(app) as client:
        created = client.post("/buyer-auth/register", json=_credentials())
        current = client.get("/buyer-auth/me")
    assert created.status_code == 201
    assert created.json()["email"] == "buyer@example.com"
    assert created.json()["role"] == "BUYER"
    assert current.status_code == 200
    assert current.json() == created.json()
    assert "timbre_buyer_session" in created.headers["set-cookie"]
    assert "HttpOnly" in created.headers["set-cookie"]
    row = fetch_one("SELECT password_hash, role FROM accounts WHERE email = ?", ("buyer@example.com",))
    assert row is not None
    assert row["role"] == "BUYER"
    assert "correct horse battery" not in row["password_hash"]


def test_buyer_login_logout_and_expiry_work_without_affecting_owner_cookie():
    with TestClient(app) as client:
        client.post("/buyer-auth/register", json=_credentials("cycle-buyer@example.com"))
        buyer = fetch_one("SELECT id FROM accounts WHERE email = ?", ("cycle-buyer@example.com",))
        assert buyer is not None
        client.cookies.clear()
        login = client.post("/buyer-auth/login", json=_credentials("cycle-buyer@example.com"))
        assert login.status_code == 200
        assert client.get("/buyer-auth/me").status_code == 200
        logout = client.post("/buyer-auth/logout")
        assert logout.status_code == 204
        assert client.get("/buyer-auth/me").status_code == 401
        client.post("/buyer-auth/login", json=_credentials("cycle-buyer@example.com"))
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        with transaction() as conn:
            conn.execute("UPDATE market_sessions SET expires_at = ? WHERE account_id = ?", (expired, buyer["id"]))
        assert client.get("/buyer-auth/me").status_code == 401


def test_buyer_logout_does_not_revoke_a_market_owner_session():
    with TestClient(app) as client:
        client.post("/market-auth/register", json=_credentials("owner-with-buyer@example.com"))
        assert client.get("/market-auth/me").status_code == 200
        client.post("/buyer-auth/register", json=_credentials("buyer-with-owner@example.com"))
        assert client.get("/buyer-auth/me").status_code == 200
        assert client.post("/buyer-auth/logout").status_code == 204
        assert client.get("/buyer-auth/me").status_code == 401
        assert client.get("/market-auth/me").status_code == 200


def test_buyer_account_cannot_log_into_or_access_market_owner_routes():
    with TestClient(app) as client:
        client.post("/buyer-auth/register", json=_credentials("separate-buyer@example.com"))
        market_login = client.post("/market-auth/login", json=_credentials("separate-buyer@example.com"))
        market_creation = client.post("/markets", json={"name": "Buyer Cannot Own This"})
    assert market_login.status_code == 401
    assert market_creation.status_code == 401


def test_market_owner_cannot_log_into_or_access_buyer_routes():
    with TestClient(app) as client:
        client.post("/market-auth/register", json=_credentials("separate-owner@example.com"))
        buyer_login = client.post("/buyer-auth/login", json=_credentials("separate-owner@example.com"))
        buyer_me = client.get("/buyer-auth/me")
    assert buyer_login.status_code == 401
    assert buyer_me.status_code == 401


def test_buyer_dependency_protects_server_routes():
    probe = APIRouter()

    @probe.get("/_test/buyer")
    def protected(buyer: BuyerAccount = Depends(current_buyer)) -> dict:
        return {"buyer_id": buyer.id}

    app.include_router(probe)
    with TestClient(app) as client:
        assert client.get("/_test/buyer").status_code == 401
        created = client.post("/buyer-auth/register", json=_credentials("protected-buyer@example.com"))
        allowed = client.get("/_test/buyer")
    assert allowed.status_code == 200
    assert allowed.json() == {"buyer_id": created.json()["id"]}


def test_buyer_registration_rejects_invalid_and_duplicate_accounts():
    with TestClient(app) as client:
        bad_email = client.post("/buyer-auth/register", json=_credentials("not-an-email"))
        short_password = client.post(
            "/buyer-auth/register", json={"email": "new-buyer@example.com", "password": "too short"}
        )
        first = client.post("/buyer-auth/register", json=_credentials("CaseBuyer@Example.com"))
        duplicate = client.post("/buyer-auth/register", json=_credentials("casebuyer@example.com"))
    assert bad_email.status_code == 422
    assert short_password.status_code == 422
    assert first.status_code == 201
    assert duplicate.status_code == 409
