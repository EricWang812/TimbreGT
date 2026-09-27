"""Feature 13: owner-scoped insights are deterministic facts; AI may only phrase them."""
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from api import market_insights
from api.main import app
from api.market_insights import compute_insight_facts, validate_explanation
from tests.test_market_orders import _market_product, _owner

NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)


def order(days_ago, units, price, status="NOT_STARTED", method="SHIP", name="Fuji Apples", history=()):
    created = (NOW - timedelta(days=days_ago)).isoformat()
    return {"createdAt": created, "stageSince": created if status == "NOT_STARTED" else None,
            "totalCents": units * price, "status": status, "fulfillmentMethod": method,
            "statusHistory": list(history),
            "items": [{"product_id": name, "product_name": name, "amount": units, "price_cents": price}]}


def facts_by_id(orders):
    return {f["id"]: f for f in compute_insight_facts(orders, NOW)}


def test_no_orders_produce_no_facts():
    assert compute_insight_facts([], NOW) == []


def test_facts_come_only_from_recorded_orders():
    orders = [
        order(3, 2, 500, name="Fuji Apples"),
        order(10, 1, 300, status="ORDER_COMPLETE", method="PICKUP", name="Oat Milk"),
        order(40, 1, 1000, status="SHIPPING"),
    ]
    facts = facts_by_id(orders)
    assert facts["waiting_to_start"]["text"] == "1 order has not been started. The oldest has been in Not Started for 3 days."
    assert facts["awaiting_handoff"]["tone"] == "attention"
    # 30-day revenue $13.00 from 2 orders against $10.00 before: up 30.0%.
    assert facts["revenue_trend"]["text"] == (
        "Revenue over the last 30 days was $13.00 from 2 orders, up 30.0% from $10.00 in the previous 30 days.")
    assert facts["top_product"]["text"].startswith("Fuji Apples sold the most units over the last 30 days: 2 units for $10.00, 77%")
    assert facts["fulfillment_mix"]["text"] == "Of all 3 orders, 2 chose shipping and 1 chose pickup."
    # Not enough samples or orders for these patterns: never guessed.
    assert "fulfillment_time" not in facts and "busiest_weekday" not in facts
    # No fact calls anything late or asserts a deadline.
    assert not any(market_insights._FORBIDDEN.search(f["text"]) for f in facts.values())


def test_thresholds_withhold_weak_patterns():
    # One order in the period: no top product; no previous period: no trend.
    facts = facts_by_id([order(1, 1, 500, status="SHIPPING")])
    assert set(facts) == set()
    # A tie in units is not reported as a single top product.
    tied = facts_by_id([order(1, 1, 500, status="SHIPPING", name="A"), order(2, 1, 500, status="SHIPPING", name="B")])
    assert "top_product" not in tied


def test_fulfillment_time_and_weekday_need_recorded_history():
    history = [{"status": "FULFILLING", "enteredAt": "2026-09-20T10:00:00+00:00"},
               {"status": "ORDER_COMPLETE", "enteredAt": "2026-09-20T12:00:00+00:00"}]
    orders = [order(7 * week, 1, 100, status="ORDER_COMPLETE", history=history) for week in range(1, 8)]
    facts = facts_by_id(orders)
    assert facts["fulfillment_time"]["text"] == (
        "Recorded preparation, from Fulfilling to Order Complete, has averaged 2 hours across 7 orders.")
    assert facts["busiest_weekday"]["text"] == f"{NOW.strftime('%A')} (UTC) had the most orders in the last 90 days: 7 of 7."


FACTS = [{"id": "revenue_trend", "tone": "info", "text": "Revenue over the last 30 days was $13.00 from 2 orders, up 30.0% from $10.00 in the previous 30 days."},
         {"id": "waiting_to_start", "tone": "attention", "text": "1 order has not been started."}]


def test_explanation_keeps_only_grounded_wording():
    result = validate_explanation({"headline": "Sales rose 30% this month.", "highlights": [
        {"factId": "revenue_trend", "explanation": "You made $13.00 from 2 orders, 30% more than before."},
        {"factId": "waiting_to_start", "explanation": "3 orders are overdue."},        # invented number and deadline
        {"factId": "unknown", "explanation": "Made up."},                              # not a supplied fact
        {"factId": "revenue_trend", "explanation": "Duplicate."},
    ]}, FACTS)
    assert result["highlights"] == [{"factId": "revenue_trend", "text": "You made $13.00 from 2 orders, 30% more than before."}]
    assert result["headline"] == "Sales rose 30% this month."
    invented = validate_explanation({"headline": "Revenue hit $500.", "highlights": [
        {"factId": "waiting_to_start", "explanation": "One order is waiting to be started."}]}, FACTS)
    assert invented["headline"] is None


def test_explanation_with_nothing_grounded_is_unavailable():
    for payload in ({"headline": "x", "highlights": [{"factId": "waiting_to_start", "explanation": "It is late."}]}, [], {"headline": "x"}):
        try:
            validate_explanation(payload, FACTS)
        except market_insights.InsightsUnavailable:
            continue
        raise AssertionError("ungrounded explanation was accepted")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload, self.status_code = payload, status_code

    def raise_for_status(self):
        import httpx
        if self.status_code >= 400:
            request = httpx.Request("POST", market_insights.RESPONSES_URL)
            raise httpx.HTTPStatusError("provider", request=request, response=httpx.Response(self.status_code, request=request))

    def json(self):
        return self.payload


def provider_output(obj):
    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(obj)}]}]}


def test_routes_are_owner_scoped_and_explanation_is_safe(monkeypatch):
    with TestClient(app) as c:
        market, _ = _market_product(c)
        path = f"/markets/{market['id']}/insights"
        empty = c.get(path)
        assert empty.status_code == 200 and empty.json()["status"] == "insufficient_data" and empty.json()["facts"] == []
        assert c.post(path + "/explanation").status_code == 409

        monkeypatch.setattr(market_insights, "market_order_dashboard",
                            lambda market_id, owner: {"orders": [order(3, 2, 500), order(40, 1, 1000, status="SHIPPING")]})
        monkeypatch.setattr(market_insights, "OPENAI_API_KEY", "")
        assert c.get(path).json()["aiAvailable"] is False
        assert "not configured" in c.post(path + "/explanation").json()["detail"]

        sent = {}
        def fake_post(url, **kwargs):
            sent.update(kwargs["json"])
            return FakeResponse(provider_output({"headline": "One order is waiting.", "highlights": [
                {"factId": "waiting_to_start", "explanation": "One order is still waiting to be started."}]}))
        monkeypatch.setattr(market_insights, "OPENAI_API_KEY", "test-key")
        monkeypatch.setattr(market_insights.httpx, "post", fake_post)
        explained = c.post(path + "/explanation")
        assert explained.status_code == 200
        assert explained.json()["highlights"][0]["factId"] == "waiting_to_start"
        assert sent["store"] is False and sent["text"]["format"]["strict"] is True
        assert sent["text"]["format"]["schema"]["properties"]["highlights"]["items"]["properties"]["factId"]["enum"] == ["waiting_to_start", "revenue_trend"]
        assert "createdAt" not in sent["input"] and "@" not in sent["input"]   # facts only, no raw records

        monkeypatch.setattr(market_insights.httpx, "post", lambda *a, **k: FakeResponse({}, 500))
        failed = c.post(path + "/explanation")
        assert failed.status_code == 503 and "still accurate" in failed.json()["detail"]

        monkeypatch.undo()
        c.cookies.clear()
        assert c.get(path).status_code == 401
        _owner(c)
        assert c.get(path).status_code == 404
        assert c.post(path + "/explanation").status_code == 404
