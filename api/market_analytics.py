"""Owner-authorized metrics from paid order snapshots, never live catalog prices."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from fastapi import APIRouter
from api.market_auth import MarketOwner
from api.market_orders import market_order_dashboard

router = APIRouter(prefix="/markets", tags=["market analytics"])
Period = Literal["7D", "30D", "1Y"]
DAYS = {"7D": 7, "30D": 30, "1Y": 365}


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def mean_cents(total, count):
    return int((Decimal(total) / count).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if count else None


def calculate_analytics(orders, period, now=None):
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=DAYS[period])
    previous_start = start - timedelta(days=DAYS[period])
    dated = [(order, instant(order["createdAt"])) for order in orders]
    current = [o for o, date in dated if date and start <= date < now]
    previous = [o for o, date in dated if date and previous_start <= date < start]
    revenue = sum(o["totalCents"] for o in current)
    previous_revenue = sum(o["totalCents"] for o in previous)
    products = {}
    daily = {}
    # Chronological iteration retains the latest purchased name for each ID.
    for order in sorted(current, key=lambda o: instant(o["createdAt"])):
        day = instant(order["createdAt"]).date().isoformat()
        daily[day] = daily.get(day, 0) + order["totalCents"]
        for item in order["items"]:
            product = products.setdefault(item["product_id"], {"productId": item["product_id"], "name": item["product_name"], "units": 0, "revenueCents": 0})
            product["name"] = item["product_name"]
            product["units"] += item["amount"]
            product["revenueCents"] += item["amount"] * item["price_cents"]
    return {"period": period, "days": DAYS[period], "start": start.isoformat(), "end": now.isoformat(),
            "revenueCents": revenue, "orderCount": len(current), "averageOrderValueCents": mean_cents(revenue, len(current)),
            "unitsSold": sum(p["units"] for p in products.values()),
            "topProducts": sorted(products.values(), key=lambda p: (-p["units"], -p["revenueCents"], p["productId"])),
            "dailyRevenue": [{"date": day, "revenueCents": amount} for day, amount in sorted(daily.items())],
            "previousRevenueCents": previous_revenue, "previousOrderCount": len(previous),
            "revenueChangePercent": round((revenue - previous_revenue) * 100 / previous_revenue, 1) if previous_revenue else None,
            "excludedUndatedOrders": sum(date is None for _, date in dated)}


@router.get("/{market_id}/analytics")
def market_analytics(market_id: str, owner: MarketOwner, period: Period = "30D"):
    orders = market_order_dashboard(market_id, owner)["orders"]
    return {"marketId": market_id, **calculate_analytics(orders, period)}


def calculate_operations(orders):
    counts = {stage: sum(o["status"] == stage for o in orders) for stage in ("NOT_STARTED", "FULFILLING", "ORDER_COMPLETE", "SHIPPING", "READY_FOR_PICKUP")}
    durations = []
    for order in orders:
        started = next((instant(h["enteredAt"]) for h in order.get("statusHistory", []) if h["status"] == "FULFILLING"), None)
        finished = next((instant(h["enteredAt"]) for h in order.get("statusHistory", []) if h["status"] == "ORDER_COMPLETE"), None)
        if started and finished and finished >= started:
            durations.append((finished - started).total_seconds())
    return {"openOrders": counts["NOT_STARTED"] + counts["FULFILLING"] + counts["ORDER_COMPLETE"],
            "fulfilling": counts["FULFILLING"],
            "waitingToShip": sum(o["status"] == "ORDER_COMPLETE" and o["fulfillmentMethod"] == "SHIP" for o in orders),
            "readyForPickup": counts["READY_FOR_PICKUP"],
            "preparationCompleted": counts["ORDER_COMPLETE"] + counts["SHIPPING"] + counts["READY_FOR_PICKUP"],
            "averageOrderValueCents": mean_cents(sum(o["totalCents"] for o in orders), len(orders)),
            "averageFulfillmentSeconds": round(sum(durations) / len(durations)) if durations else None,
            "fulfillmentSampleCount": len(durations), "orderCount": len(orders)}


@router.get("/{market_id}/operations")
def market_operations(market_id: str, owner: MarketOwner):
    return {"marketId": market_id, **calculate_operations(market_order_dashboard(market_id, owner)["orders"])}
