"""Phase 0 scaffold checks: both services boot, create their schema, and only
accept cross-origin requests from the web origin."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import db as merchant_db
from api.config import MERCHANT_DB
from api.main import app as merchant_app
from issuer import db as issuer_db
from issuer.config import ISSUER_DB, WEB_ORIGIN
from issuer.main import app as issuer_app

APPS = {"merchant": merchant_app, "issuer": issuer_app}
FOREIGN_ORIGIN = "http://evil.example"


def test_databases_are_temporary():
    tmp = Path(tempfile.gettempdir()).resolve()
    assert tmp in MERCHANT_DB.parents
    assert tmp in ISSUER_DB.parents


@pytest.mark.parametrize(("name", "body"), [
    ("merchant", {"status": "ok"}),
    ("issuer", {"status": "ok", "encoder": "resident"}),
])
def test_healthz(name, body):
    with TestClient(APPS[name]) as client:
        res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == body


@pytest.mark.parametrize(
    ("app", "db", "tables"),
    [
        (merchant_app, merchant_db, {"products", "orders"}),
        (issuer_app, issuer_db,
         {"users", "payment_tokens", "templates", "enroll_labels", "enroll_samples",
          "sessions", "verifications", "passkeys"}),
    ],
)
def test_schema_created_on_startup(app, db, tables):
    with TestClient(app):
        rows = db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table'")
    assert tables <= {r["name"] for r in rows}


@pytest.mark.parametrize("name", APPS)
def test_cors_allows_only_web_origin(name):
    with TestClient(APPS[name]) as client:
        ok = client.get("/healthz", headers={"Origin": WEB_ORIGIN})
        bad = client.get("/healthz", headers={"Origin": FOREIGN_ORIGIN})
    assert ok.headers.get("access-control-allow-origin") == WEB_ORIGIN
    assert "access-control-allow-origin" not in bad.headers
