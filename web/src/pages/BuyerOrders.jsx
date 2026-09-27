import { useEffect, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { CheckIcon, TruckIcon } from "../components/Icons.jsx";
import { buyAgain, getBuyerOrder, getBuyerOrders, getCartProducts } from "../lib/api.js";
import { formatCents } from "../lib/money.js";
import { useCart } from "../lib/cart.jsx";
import { signInHref } from "../lib/account.js";

// Each order is one full-width card, laid out the way large stores do it: a
// header strip (placed, total, ship to, order number), then the status, a
// progress tracker, the items with their own Buy it again, and order actions.
const STEPS = {
  SHIP: ["NOT_STARTED", "FULFILLING", "ORDER_COMPLETE", "SHIPPING"],
  PICKUP: ["NOT_STARTED", "FULFILLING", "ORDER_COMPLETE", "READY_FOR_PICKUP"],
};
const STEP_LABELS = { NOT_STARTED: "Ordered", FULFILLING: "Preparing", ORDER_COMPLETE: "Packed", SHIPPING: "Shipped", READY_FOR_PICKUP: "Ready for pickup" };
const FILTERS = [["ALL", "All"], ["ACTIVE", "In progress"], ["SHIP", "Shipping"], ["PICKUP", "Pickup"]];

export function headline(order) {
  const pickup = order.fulfillmentMethod === "PICKUP";
  switch (order.status) {
    case "NOT_STARTED": return ["Order placed", `${order.market.name} has your order and will start preparing it soon.`];
    case "FULFILLING": return ["Being prepared", `${order.market.name} is preparing your order.`];
    case "ORDER_COMPLETE": return [pickup ? "Packed, getting ready for pickup" : "Packed, waiting to ship", "Your items are packed."];
    case "SHIPPING": return ["Shipped", order.localDriver ? "A local driver is handling this delivery." : order.carrier ? `On its way with ${order.carrier}.` : "Your order is on its way."];
    case "READY_FOR_PICKUP": return ["Ready for pickup", order.pickupAt ? `Pick it up at ${order.pickupAt.addressLine1}, ${order.pickupAt.city}.` : "Your order is ready for pickup."];
    default: return [order.status, ""];
  }
}

export const placedOn = (iso) => new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
export const shortId = (id) => id.slice(0, 8).toUpperCase();

// Current photos and availability for past items. An item the market no longer
// sells has no entry, so its Buy it again is shown as unavailable.
export function useCurrentProducts(orders) {
  const [products, setProducts] = useState({});
  const key = [...new Set(orders.flatMap((o) => o.items.map((i) => i.product_id)).filter(Boolean))].sort().join(",");
  useEffect(() => {
    if (!key) return;
    let active = true;
    getCartProducts(key.split(",")).then(({ products: list }) => {
      if (active) setProducts(Object.fromEntries(list.map((p) => [p.id, p])));
    }, () => { /* photos are decoration; the order itself still shows */ });
    return () => { active = false; };
  }, [key]);
  return products;
}

export function SignInPrompt({ what }) {
  return <p role="alert">Sign in as a buyer to see {what}. <a href={signInHref("buyer")}>Sign in or create a buyer account</a></p>;
}

function ProgressTracker({ order }) {
  const steps = STEPS[order.fulfillmentMethod] ?? STEPS.SHIP;
  const current = steps.indexOf(order.status);
  return <ol className="purchase-progress" aria-label="Order progress">
    {steps.map((step, index) => {
      const state = index < current ? "done" : index === current ? "current" : "upcoming";
      return <li key={step} className={`is-${state}`} aria-current={state === "current" ? "step" : undefined}>
        <span className="purchase-progress-dot" aria-hidden="true">{state !== "upcoming" && <CheckIcon size={14} />}</span>
        <span>{STEP_LABELS[step]}<span className="visually-hidden">{state === "done" ? ", done" : state === "current" ? ", current step" : ", not yet"}</span></span>
      </li>;
    })}
  </ol>;
}

function OrderCard({ order, products, detailed = false, fullAddress }) {
  const cart = useCart();
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [title, detail] = headline(order);
  const destination = order.fulfillmentMethod === "PICKUP"
    ? ["Pick up at", order.pickupAt ? `${order.pickupAt.city}, ${order.pickupAt.stateRegion}` : order.pickupAddress ? `${order.pickupAddress.city}, ${order.pickupAddress.stateRegion}` : "Market pickup"]
    : ["Ship to", order.shipTo?.recipientName ?? order.shippingAddress?.recipientName ?? "Saved address"];

  function addOne(item) {
    cart.adjust(item.product_id, 1);
    setMessage({ text: `Added ${item.product_name} to your cart.`, cart: true });
  }
  async function addAll() {
    setBusy(true); setMessage(null);
    try {
      const result = await buyAgain(order.id);
      result.items.forEach((item) => cart.adjust(item.productId, item.quantity));
      const notes = [result.unavailable.length && `${result.unavailable.length} no longer available`, result.priceChanged.length && `${result.priceChanged.length} with a new price`].filter(Boolean);
      setMessage({ text: `Added ${result.items.length} ${result.items.length === 1 ? "item" : "items"} to your cart${notes.length ? ` (${notes.join(", ")})` : ""}.`, cart: result.items.length > 0 });
    } catch {
      setMessage({ text: "These items could not be added. Try again.", error: true });
    } finally { setBusy(false); }
  }

  return <article className="purchase-card" aria-labelledby={`order-${order.id}`}>
    <header className="purchase-card-head">
      <dl>
        <div><dt>Order placed</dt><dd>{placedOn(order.createdAt)}</dd></div>
        <div><dt>Total</dt><dd>{formatCents(order.totalCents)}</dd></div>
        <div><dt>{destination[0]}</dt><dd>{destination[1]}</dd></div>
        <div><dt>Sold by</dt><dd>{order.market.name}</dd></div>
      </dl>
      <div className="purchase-card-id">
        <span>Order # {shortId(order.id)}</span>
        {!detailed && <a href={`#/buyer-orders/${order.id}`}>View order details</a>}
      </div>
    </header>
    <div className="purchase-card-body">
      <div className="purchase-card-main">
        <h2 id={`order-${order.id}`} className="purchase-status">{title}</h2>
        {detail && <p className="purchase-status-detail">{detail}</p>}
        <ProgressTracker order={order} />
        <ul className="purchase-items">
          {order.items.map((item, index) => {
            const current = products[item.product_id];
            return <li key={`${item.product_id}-${index}`} className="purchase-item">
              {current?.image_url
                ? <img className="purchase-thumb" src={current.image_url} alt="" width="88" height="88" loading="lazy" />
                : <span className="purchase-thumb" aria-hidden="true" />}
              <div className="purchase-item-info">
                <p className="purchase-item-name">{item.product_name}</p>
                <p className="note">Qty {item.amount} · {formatCents(item.price_cents)} each</p>
                {current
                  ? <button type="button" className="btn btn-secondary purchase-again" onClick={() => addOne(item)}>Buy it again</button>
                  : <p className="note">No longer sold by {order.market.name}.</p>}
              </div>
              <p className="purchase-item-total">{formatCents(item.amount * item.price_cents)}</p>
            </li>;
          })}
        </ul>
        {detailed && fullAddress}
      </div>
      <aside className="purchase-card-actions" aria-label={`Actions for order ${shortId(order.id)}`}>
        {!detailed && <a className="btn btn-primary" href={`#/buyer-orders/${order.id}`}>View order details</a>}
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={addAll}>{busy ? "Adding…" : "Buy all again"}</button>
        {order.carrier && order.trackingNumber && <div className="purchase-tracking"><TruckIcon size={18} /> <span>{order.carrier} tracking<br /><strong className="break-anywhere">{order.trackingNumber}</strong></span></div>}
        <div aria-live="polite">
          {message && <p className={message.error ? "message-error" : "purchase-message"}>{message.text}{message.cart && <> <a href="#/checkout">Go to checkout</a></>}</p>}
        </div>
      </aside>
    </div>
  </article>;
}

export function BuyerOrders() {
  const [state, setState] = useState({ status: "loading", orders: [] });
  const [filter, setFilter] = useState("ALL");
  useEffect(() => {
    let active = true;
    getBuyerOrders().then(({ orders }) => { if (active) setState({ status: "ready", orders }); },
      (error) => { if (active) setState({ status: error.status === 401 ? "unauthorized" : "error", orders: [] }); });
    return () => { active = false; };
  }, []);
  const products = useCurrentProducts(state.orders);
  // Shipping and Pickup filter by how the order arrives; In progress is still being prepared.
  const filtered = state.orders.filter((order) => filter === "ALL"
    || (filter === "ACTIVE" && !["SHIPPING", "READY_FOR_PICKUP"].includes(order.status))
    || order.fulfillmentMethod === filter);
  return <section className="stack purchase-history">
    <PageHeading>Your orders</PageHeading>
    {state.status === "loading" && <p className="note" role="status" aria-busy="true">Loading orders…</p>}
    {state.status === "unauthorized" && <SignInPrompt what="your orders" />}
    {state.status === "error" && <p className="message-error" role="alert">Unable to load orders. Refresh to try again.</p>}
    {state.status === "ready" && !state.orders.length && <div className="purchase-empty"><p>You have no orders yet.</p><a className="btn btn-primary" href="#/">Start shopping</a></div>}
    {state.status === "ready" && state.orders.length > 0 && <>
      <div className="purchase-toolbar">
        <div className="fact-pills" role="group" aria-label="Filter orders">{FILTERS.map(([id, label]) => <button className="chip" type="button" key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>)}</div>
        <p className="note" role="status">{filtered.length} {filtered.length === 1 ? "order" : "orders"}</p>
      </div>
      {!filtered.length ? <p className="note">No orders match this filter.</p>
        : <ul className="purchase-list">{filtered.map((order) => <li key={order.id}><OrderCard order={order} products={products} /></li>)}</ul>}
    </>}
  </section>;
}

function Address({ label, address }) {
  return <section className="purchase-address"><h3>{label}</h3><address>
    {address.recipientName && <>{address.recipientName}<br /></>}{address.addressLine1}{address.addressLine2 && <><br />{address.addressLine2}</>}<br />{address.city}, {address.stateRegion} {address.postalCode}<br />{address.country}
  </address></section>;
}

export function BuyerOrderDetails({ orderId }) {
  const [state, setState] = useState({ status: "loading", order: null });
  useEffect(() => {
    let active = true;
    getBuyerOrder(orderId).then((order) => { if (active) setState({ status: "ready", order }); },
      (error) => { if (active) setState({ status: error.status === 401 ? "unauthorized" : error.status === 404 ? "missing" : "error", order: null }); });
    return () => { active = false; };
  }, [orderId]);
  const products = useCurrentProducts(state.order ? [state.order] : []);
  const shell = (body) => <section className="stack purchase-history"><p><a href="#/buyer-orders">← Back to your orders</a></p><PageHeading>Order details</PageHeading>{body}</section>;
  if (state.status === "loading") return shell(<p className="note" role="status" aria-busy="true">Loading order…</p>);
  if (state.status === "error") return shell(<p className="message-error" role="alert">Unable to load this order. Refresh to try again.</p>);
  if (state.status === "unauthorized") return shell(<SignInPrompt what="this order" />);
  if (state.status === "missing") return shell(<p role="alert">This order is not in your account.</p>);
  const order = state.order;
  const itemsCents = order.items.reduce((sum, item) => sum + item.amount * item.price_cents, 0);
  const fullAddress = <div className="purchase-details-grid">
    {order.shippingAddress && <Address label="Shipping address" address={order.shippingAddress} />}
    {order.pickupAddress && <Address label="Pickup address" address={order.pickupAddress} />}
    <section className="purchase-address"><h3>Order summary</h3>
      <table className="checkout-totals"><caption className="visually-hidden">Order summary</caption><tbody>
        <tr><th scope="row">Items</th><td>{formatCents(itemsCents)}</td></tr>
        <tr><th scope="row">Tax and delivery</th><td>{formatCents(order.totalCents - itemsCents)}</td></tr>
        <tr className="checkout-total-row"><th scope="row">Total paid</th><td>{formatCents(order.totalCents)}</td></tr>
      </tbody></table>
    </section>
  </div>;
  return shell(<OrderCard order={order} products={products} detailed fullAddress={fullAddress} />);
}
