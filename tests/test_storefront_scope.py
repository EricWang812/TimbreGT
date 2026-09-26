"""Persisted storefront and shopping share a request-local market scope."""
import uuid
from fastapi.testclient import TestClient
from api.main import app
from api import catalog, shopping, agentic_shopping
from tests.test_agentic_intent import intent_payload
from api.openai_intent import ShoppingIntent


def test_selected_market_scopes_both_shopping_paths_and_resets(monkeypatch):
    seen = []
    def rank(hypotheses, products):
        seen.append(products)
        return {"product_id": products[0]["id"] if products else None}
    monkeypatch.setattr(shopping, "rerank", rank)
    def extract(text):
        seen.append(catalog.list_catalog())
        return ShoppingIntent.model_validate(intent_payload())
    monkeypatch.setattr(agentic_shopping, "extract_shopping_intent", extract)
    with TestClient(app) as c:
        c.post("/market-auth/register", json={"email": f"scope-{uuid.uuid4()}@example.com", "password": "correct horse battery"})
        markets = [c.post("/markets", json={"name": name}).json()["id"] for name in ("First Market", "Second Market", "Empty Market")]
        products = [c.post(f"/markets/{m}/products", json={"name": "Apple", "price": i + 1}).json()["id"] for i, m in enumerate(markets[:2])]
        for i, market in enumerate(markets[:2]):
            assert c.post(f"/shopping/text?marketId={market}", json={"text": "apple"}).status_code == 200
            assert [p["id"] for p in seen[-1]] == [products[i]]
            assert c.post(f"/agentic-shopping/intent?marketId={market}", json={"transcript": "apple"}).status_code == 200
            assert [p["id"] for p in seen[-1]] == [products[i]]
        assert catalog.selected_market.get() is None
        assert c.post("/shopping/text?marketId=missing", json={"text": "apple"}).status_code == 404
        assert c.get(f"/storefront/markets/{markets[2]}/products").json()["products"] == []
        assert markets[2] in [m["id"] for m in c.get("/storefront/markets").json()["markets"]]
