import { formatCents } from "../lib/money.js";
import { statusLabel, fulfillmentLabel, attention } from "../lib/marketOrders.js";

function Address({ title, address }) {
  if (!address) return null;
  return <section><h3>{title}</h3><address>{[address.recipientName, address.addressLine1, address.addressLine2, [address.city, address.stateRegion, address.postalCode].filter(Boolean).join(", "), address.country].filter(Boolean).map((line, i) => <div key={i}>{line}</div>)}</address></section>;
}
export default function MarketOrderDetails({ order, marketId, onMove, busy }) {
  return <article className="stack order-detail">
    <a href={`#/market-dashboard/${marketId}`}>Back to overview</a>
    <h2>Order {order.id}</h2>
    <p>{statusLabel(order.status)} · {fulfillmentLabel(order)}</p>
    {attention(order) && <p className="order-attention">{attention(order)}</p>}
    <p>Created: <time dateTime={order.createdAt}>{new Date(order.createdAt).toLocaleString()}</time></p>
    <ul className="checkout-lines">{order.items.map((item, i) => <li className="checkout-line" key={`${item.product_id}-${i}`}><div><strong>{item.product_name}</strong><p>{item.amount} × {formatCents(item.price_cents)}</p>{item.quantity_value && <p>{item.quantity_value} {item.quantity_unit} per item</p>}</div><strong>{formatCents(item.price_cents * item.amount)}</strong></li>)}</ul>
    <p><strong>Total: {formatCents(order.totalCents)}</strong></p>
    <Address title="Shipping address" address={order.shippingAddress} />
    <Address title="Pickup information" address={order.pickupAddress} />
    {order.carrier && <p>{order.carrier}: {order.trackingNumber}</p>}
    {order.localDriver && <p>{order.deliveryMessage}</p>}
    <div className="management-actions">{order.allowedTransitions?.map((status) => <button className="btn btn-primary" disabled={busy} key={status} onClick={() => onMove(order.id, status)}>Move to {statusLabel(status)}</button>)}</div>
  </article>;
}
