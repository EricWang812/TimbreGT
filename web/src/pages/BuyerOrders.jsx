import { useEffect, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { buyAgain, getBuyerOrder, getBuyerOrders } from "../lib/api.js";
import { formatCents } from "../lib/money.js";
import { useCart } from "../lib/cart.jsx";

const LABELS = { NOT_STARTED: "Not Started", FULFILLING: "Fulfilling", ORDER_COMPLETE: "Order Complete", SHIPPING: "Shipping", READY_FOR_PICKUP: "Ready for Pickup" };
const stages = ["NOT_STARTED", "FULFILLING", "ORDER_COMPLETE", "SHIPPING", "READY_FOR_PICKUP"];
const status = (value) => LABELS[value] ?? value;

export function BuyerOrders() {
  const [state, setState] = useState({ status: "loading", orders: [] });
  const [filter, setFilter] = useState("ALL");
  useEffect(() => { getBuyerOrders().then(({ orders }) => setState({ status: "ready", orders }), () => setState({ status: "error", orders: [] })); }, []);
  const filtered = state.orders.filter((order) => filter === "ALL" || (filter === "ACTIVE" && !["SHIPPING", "READY_FOR_PICKUP"].includes(order.status)) || order.status === filter);
  return <section className="stack"><PageHeading>Orders</PageHeading>
    <div className="fact-pills">{[["ALL", "All"], ["ACTIVE", "Active"], ["SHIPPING", "Shipping"], ["READY_FOR_PICKUP", "Pickup"]].map(([id, label]) => <button className="chip" type="button" key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>)}</div>
    {state.status === "loading" && <p className="note" aria-busy="true">Loading orders…</p>}{state.status === "error" && <p className="message-error" role="alert">Unable to load orders.</p>}
    {state.status === "ready" && (!filtered.length ? <p className="note">No orders match this filter.</p> : <ul className="checkout-lines">{filtered.map((order) => <li className="checkout-line" key={order.id}><div className="checkout-line-info"><p className="checkout-line-name"><a href={`#/buyer-orders/${order.id}`}>{order.market.name}</a></p><p className="checkout-line-unit">{new Date(order.createdAt).toLocaleDateString()} · {order.fulfillmentMethod} · {status(order.status)}</p></div><p>{formatCents(order.totalCents)}</p></li>)}</ul>)}</section>;
}

export function BuyerOrderDetails({ orderId }) {
  const cart = useCart();
  const [state, setState] = useState({ status: "loading", order: null });
  const [reorder, setReorder] = useState(null);
  useEffect(() => { getBuyerOrder(orderId).then((order) => setState({ status: "ready", order }), () => setState({ status: "error", order: null })); }, [orderId]);
  if (state.status === "loading") return <section className="stack"><PageHeading>Order details</PageHeading><p className="note" aria-busy="true">Loading order…</p></section>;
  if (state.status === "error") return <section className="stack"><PageHeading>Order details</PageHeading><p className="message-error" role="alert">Unable to load this order.</p></section>;
  const order = state.order; const terminal = order.fulfillmentMethod === "SHIP" ? "SHIPPING" : "READY_FOR_PICKUP";
  const timeline = stages.filter((stage) => stage !== (terminal === "SHIPPING" ? "READY_FOR_PICKUP" : "SHIPPING"));
  async function addOrderAgain() {
    setReorder({ status: "loading" });
    try {
      const result = await buyAgain(orderId);
      result.items.forEach((item) => cart.adjust(item.productId, item.quantity));
      setReorder({ status: "ready", ...result });
    } catch { setReorder({ status: "error" }); }
  }
  return <section className="stack"><p><a href="#/buyer-orders">Back to orders</a></p><PageHeading>{order.market.name}</PageHeading><p>{new Date(order.createdAt).toLocaleString()} · {status(order.status)} · {order.fulfillmentMethod}</p>
    <ol className="fact-pills" aria-label="Order progress">{timeline.map((stage) => <li key={stage}>{status(stage)}{stage === order.status ? " (current)" : ""}</li>)}</ol>
    <ul className="checkout-lines">{order.items.map((item) => <li className="checkout-line" key={`${item.product_name}-${item.quantity_unit}`}><div className="checkout-line-info"><p className="checkout-line-name">{item.product_name}</p><p className="checkout-line-unit">{item.amount} × {formatCents(item.price_cents)}</p></div><p>{formatCents(item.amount * item.price_cents)}</p></li>)}</ul><p><strong>Total: {formatCents(order.totalCents)}</strong></p><p><button className="btn btn-primary" type="button" disabled={reorder?.status === "loading"} onClick={addOrderAgain}>Buy Again</button></p>{reorder?.status === "ready" && <p role="status">{reorder.items.length} items added. {reorder.unavailable.length} unavailable. {reorder.priceChanged.length} prices changed. <a href="#/">View cart</a></p>}{reorder?.status === "error" && <p className="message-error" role="alert">Unable to add these items to your cart.</p>}
    {order.shippingAddress && <p>Shipping to: {order.shippingAddress.addressLine1}, {order.shippingAddress.city}, {order.shippingAddress.stateRegion} {order.shippingAddress.postalCode}</p>}{order.pickupAddress && <p>Pickup at: {order.pickupAddress.addressLine1}, {order.pickupAddress.city}, {order.pickupAddress.stateRegion}</p>}{order.carrier && <p>{order.carrier} tracking: {order.trackingNumber}</p>}{order.localDriver && <p>Local Driver Delivery</p>}
  </section>;
}
