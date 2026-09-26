import { useState } from "react";
import { formatCents } from "../lib/money.js";
import { ORDER_STAGES, statusLabel, fulfillmentLabel, orderLink, attention, visibleOrders } from "../lib/marketOrders.js";
export default function MarketOrders({ orders, marketId }) {
  const [filter, setFilter] = useState("ALL");
  const [sort, setSort] = useState("NEWEST");
  const shown = visibleOrders(orders, filter, sort);
  return <section className="stack">
    <div className="management-controls">
      <label>Status<select value={filter} onChange={(e) => setFilter(e.target.value)}>{[["ALL", "All"], ...ORDER_STAGES].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label>Sort orders<select value={sort} onChange={(e) => setSort(e.target.value)}><option value="NEWEST">Newest</option><option value="OLDEST">Oldest</option><option value="VALUE">Highest value</option></select></label>
    </div>
    <p className="note">Attention labels describe the current stage and elapsed time. They do not imply a delivery deadline.</p>
    {!shown.length ? <p>No orders match this filter.</p> : <ul className="order-list">{shown.map((order) => <li className="order-card" key={order.id}>
      <a href={orderLink(marketId, order.id)}>Order {order.id}</a>
      <strong>{formatCents(order.totalCents)}</strong><p>{statusLabel(order.status)} · {fulfillmentLabel(order)}</p>
      <p>{new Date(order.createdAt).toLocaleString()} · {order.items.reduce((n, i) => n + i.amount, 0)} items</p>
      {attention(order) && <p className="order-attention">{attention(order)}</p>}
    </li>)}</ul>}
  </section>;
}
