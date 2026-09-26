from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from api.main import app
from api.market_analytics import calculate_analytics
from tests.test_market_orders import _market_product, _owner

NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)
def order(days, amount, price, product="deleted-id"):
    return {"createdAt": (NOW-timedelta(days=days)).isoformat(), "totalCents": amount*price,
            "items": [{"product_id": product, "product_name": "Historical name", "amount": amount, "price_cents": price}]}

def test_period_boundaries_snapshot_prices_deleted_products_and_comparison():
    data = calculate_analytics([order(1, 2, 500), order(7, 1, 200), order(8, 2, 300), order(14, 1, 400), order(15, 9, 900), order(-1, 1, 999)], "7D", NOW)
    assert data["revenueCents"] == 1200 and data["orderCount"] == 2
    assert data["averageOrderValueCents"] == 600 and data["unitsSold"] == 3
    assert data["previousRevenueCents"] == 1000 and data["revenueChangePercent"] == 20
    assert data["topProducts"][0]["name"] == "Historical name"
    assert data["topProducts"][0]["revenueCents"] == 1200

def test_empty_periods_never_divide_by_zero():
    for period in ("7D", "30D", "1Y"):
        data = calculate_analytics([], period, NOW)
        assert data["revenueCents"] == 0
        assert data["averageOrderValueCents"] is None and data["revenueChangePercent"] is None
        assert data["topProducts"] == []

def test_analytics_requires_market_owner_and_rejects_other_owners():
    with TestClient(app) as c:
        market, _ = _market_product(c)
        path = f"/markets/{market['id']}/analytics"
        assert c.get(path).status_code == 200
        assert c.get(path + "?period=unsupported").status_code == 422
        c.cookies.clear()
        assert c.get(path).status_code == 401
        _owner(c)
        assert c.get(path).status_code == 404


def test_operations_uses_only_recorded_fulfillment_intervals():
    from api.market_analytics import calculate_operations
    first = {**order(1, 2, 500), "status": "ORDER_COMPLETE", "fulfillmentMethod": "SHIP", "statusHistory": [
        {"status": "FULFILLING", "enteredAt": "2026-09-25T10:00:00+00:00"},
        {"status": "ORDER_COMPLETE", "enteredAt": "2026-09-25T11:00:00+00:00"}]}
    older = {**order(5, 1, 200), "status": "READY_FOR_PICKUP", "fulfillmentMethod": "PICKUP", "statusHistory": []}
    m = calculate_operations([first, older])
    assert m["openOrders"] == 1 and m["waitingToShip"] == 1 and m["readyForPickup"] == 1
    assert m["preparationCompleted"] == 2
    assert m["averageFulfillmentSeconds"] == 3600 and m["fulfillmentSampleCount"] == 1
    assert calculate_operations([older])["averageFulfillmentSeconds"] is None
    assert calculate_operations([])["averageOrderValueCents"] is None
