"""Feature 22 marketplace search is read-only and market-aware."""
import uuid
from fastapi.testclient import TestClient
from api.main import app


def test_agentic_marketplace_search_returns_market_and_normalized_value_data():
    with TestClient(app) as client:
        client.post("/market-auth/register", json={"email": f"agent-{uuid.uuid4()}@example.com", "password": "correct horse battery"})
        market = client.post("/markets", json={"name": "Agent Market"}).json()
        product = client.post(f"/markets/{market['id']}/products", json={"name": "Organic Apples", "price": 4, "quantity": 2, "unit": "lb"}).json()
        result = client.get("/agentic-shopping/commerce/marketplace-products", params={"query": "apples"})
    assert result.status_code == 200
    found = result.json()["products"][0]
    assert found["id"] == product["id"]
    assert found["marketName"] == "Agent Market"
    assert found["normalizedUnit"] == "mg"
    assert found["normalizedQuantityPerDollar"] is not None
