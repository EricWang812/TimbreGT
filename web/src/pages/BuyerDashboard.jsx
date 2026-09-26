import { useEffect, useMemo, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { getBuyerOrders } from "../lib/api.js";
import { formatCents } from "../lib/money.js";

const ACTIVE = new Set(["NOT_STARTED", "FULFILLING", "ORDER_COMPLETE", "SHIPPING", "READY_FOR_PICKUP"]);
const LABELS = { NOT_STARTED: "Not Started", FULFILLING: "Fulfilling", ORDER_COMPLETE: "Order Complete", SHIPPING: "Shipping", READY_FOR_PICKUP: "Ready for Pickup" };

export default function BuyerDashboard() {
  const [state, setState] = useState({ status: "loading", orders: [] });
  useEffect(() => {
    let cancelled = false;
    getBuyerOrders().then(
      ({ orders }) => !cancelled && setState({ status: "ready", orders }),
      () => !cancelled && setState({ status: "error", orders: [] }),
    );
    return () => { cancelled = true; };
  }, []);
  const metrics = useMemo(() => {
    const now = Date.now();
    const month = state.orders.filter((order) => now - new Date(order.createdAt).getTime() <= 30 * 864e5);
    const marketCounts = new Map();
    state.orders.forEach((order) => marketCounts.set(order.market.name, (marketCounts.get(order.market.name) ?? 0) + 1));
    const favorite = [...marketCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
    const itemCounts = new Map();
    state.orders.forEach((order) => order.items.forEach((item) => itemCounts.set(item.product_name, (itemCounts.get(item.product_name) ?? 0) + item.amount)));
    const frequentItem = [...itemCounts.entries()].sort((a, b) => b[1] - a[1])[0] ?? null;
    const fulfillmentCounts = new Map();
    state.orders.forEach((order) => fulfillmentCounts.set(order.fulfillmentMethod, (fulfillmentCounts.get(order.fulfillmentMethod) ?? 0) + 1));
    const fulfillment = [...fulfillmentCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
    return { spend: month.reduce((sum, order) => sum + order.totalCents, 0), count: month.length,
      active: state.orders.filter((order) => ACTIVE.has(order.status)).length, favorite, frequentItem, fulfillment };
  }, [state.orders]);
  return <section className="stack">
    <PageHeading>Buyer Dashboard</PageHeading>
    {state.status === "loading" && <p className="note" aria-busy="true">Loading your order history…</p>}
    {state.status === "error" && <p className="message-error" role="alert">Unable to load your order history. Sign in as a buyer and try again.</p>}
    {state.status === "ready" && <>
      <div className="fact-pills"><span>30-day spending: {formatCents(metrics.spend)}</span><span>Orders in the last 30 days: {metrics.count}</span><span>Active deliveries or pickups: {metrics.active}</span>{metrics.favorite && <span>Most visited market: {metrics.favorite}</span>}</div>
      {state.orders.length > 1 && <section><h2>Your shopping insights</h2><ul>{metrics.favorite && <li>You order from {metrics.favorite} most often.</li>}{metrics.frequentItem && <li>Your most purchased item is {metrics.frequentItem[0]} ({metrics.frequentItem[1]} total).</li>}{metrics.fulfillment && <li>Your most common fulfillment choice is {metrics.fulfillment.toLowerCase()}.</li>}</ul></section>}
      {!state.orders.length ? <p className="note">You have no marketplace orders yet.</p> : <section><h2>Recent orders</h2><ul className="checkout-lines">{state.orders.slice(0, 5).map((order) => <li className="checkout-line" key={order.id}><div className="checkout-line-info"><p className="checkout-line-name">{order.market.name}</p><p className="checkout-line-unit">{new Date(order.createdAt).toLocaleDateString()} · {order.fulfillmentMethod}</p></div><div><p>{formatCents(order.totalCents)}</p><p className="note">{LABELS[order.status] ?? order.status}</p></div></li>)}</ul></section>}
    </>}
  </section>;
}
