import { useEffect, useMemo, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { BagIcon, CheckIcon, TruckIcon, UserIcon, WavesIcon } from "../components/Icons.jsx";
import { useAccountSessions } from "../lib/account.js";
import { getBuyerOrders } from "../lib/api.js";
import { useCart } from "../lib/cart.jsx";
import { formatCents } from "../lib/money.js";
import { SignInPrompt, headline, placedOn, useCurrentProducts } from "./BuyerOrders.jsx";

const PREPARING = new Set(["NOT_STARTED", "FULFILLING", "ORDER_COMPLETE"]);
const ON_THE_WAY = new Set(["SHIPPING", "READY_FOR_PICKUP"]);
const DAY_MS = 864e5;

// Everything here is computed from the buyer's own recorded orders; nothing is
// estimated or invented. Empty and small histories show fewer, honest cards.
function useMetrics(orders) {
  return useMemo(() => {
    const now = Date.now();
    const recent = orders.filter((o) => now - new Date(o.createdAt).getTime() <= 30 * DAY_MS);
    const count = (key) => orders.reduce((map, o) => map.set(key(o), (map.get(key(o)) ?? 0) + 1), new Map());
    const top = (map) => [...map.entries()].sort((a, b) => b[1] - a[1])[0] ?? null;
    const units = new Map();
    orders.forEach((o) => o.items.forEach((i) => {
      const entry = units.get(i.product_id) ?? { productId: i.product_id, name: i.product_name, units: 0, market: o.market.name };
      entry.units += i.amount;
      units.set(i.product_id, entry);
    }));
    return {
      spend: recent.reduce((sum, o) => sum + o.totalCents, 0),
      recentCount: recent.length,
      preparing: orders.filter((o) => PREPARING.has(o.status)).length,
      onTheWay: orders.filter((o) => ON_THE_WAY.has(o.status)).length,
      favoriteMarket: top(count((o) => o.market.name)),
      method: top(count((o) => o.fulfillmentMethod)),
      mostBought: [...units.values()].sort((a, b) => b.units - a.units),
      lifetime: orders.reduce((sum, o) => sum + o.totalCents, 0),
    };
  }, [orders]);
}

function firstName(email) {
  const name = (email ?? "").split("@")[0].split(/[._-]/)[0];
  return name ? name[0].toUpperCase() + name.slice(1) : "there";
}

function Stat({ icon, label, value, caption }) {
  return <div className="dash-stat">
    <span className="dash-stat-icon" aria-hidden="true">{icon}</span>
    <div><p className="dash-stat-label">{label}</p><p className="dash-stat-value">{value}</p>{caption && <p className="dash-stat-caption">{caption}</p>}</div>
  </div>;
}

function RecentOrder({ order, products }) {
  const [title] = headline(order);
  const thumbs = order.items.slice(0, 3);
  const itemCount = order.items.reduce((n, i) => n + i.amount, 0);
  return <li className="dash-order">
    <div className="dash-order-thumbs" aria-hidden="true">
      {thumbs.map((item, i) => products[item.product_id]?.image_url
        ? <img key={i} src={products[item.product_id].image_url} alt="" width="56" height="56" loading="lazy" />
        : <span key={i} />)}
      {order.items.length > 3 && <span className="dash-order-more">+{order.items.length - 3}</span>}
    </div>
    <div className="dash-order-info">
      <p className="dash-order-title"><span className={`dash-badge ${ON_THE_WAY.has(order.status) ? "is-ready" : ""}`}>{title}</span></p>
      <p className="note">{order.market.name} · {placedOn(order.createdAt)} · {itemCount} {itemCount === 1 ? "item" : "items"}</p>
    </div>
    <p className="dash-order-total">{formatCents(order.totalCents)}</p>
    <a className="btn btn-secondary dash-order-link" href={`#/buyer-orders/${order.id}`} aria-label={`View order from ${order.market.name}, ${placedOn(order.createdAt)}`}>View</a>
  </li>;
}

function BuyAgain({ items, products }) {
  const cart = useCart();
  const [added, setAdded] = useState(null);
  const available = items.filter((i) => products[i.productId]).slice(0, 4);
  if (!available.length) return null;
  return <section className="dash-panel" aria-labelledby="buy-again-title">
    <h2 id="buy-again-title">Buy it again</h2>
    <ul className="dash-again">
      {available.map((item) => {
        const p = products[item.productId];
        return <li key={item.productId}>
          {p.image_url ? <img src={p.image_url} alt="" width="64" height="64" loading="lazy" /> : <span className="dash-again-blank" aria-hidden="true" />}
          <div className="dash-again-info">
            <p className="dash-again-name">{p.name}</p>
            <p className="note">{formatCents(p.price_cents)} · bought {item.units}×</p>
          </div>
          <button type="button" className="btn btn-primary dash-again-add" aria-label={`Add ${p.name} to cart`}
            onClick={() => { cart.adjust(item.productId, 1); setAdded(p.name); }}>Add</button>
        </li>;
      })}
    </ul>
    <p className="purchase-message" aria-live="polite">{added && <>Added {added} to your cart. <a href="#/checkout">Checkout</a></>}</p>
  </section>;
}

const TILES = [
  ["#/buyer-orders", "Your orders", "Track, view details, or buy again", <TruckIcon size={24} />],
  ["#/addresses", "Addresses", "Where your orders ship", <WavesIcon size={24} />],
  ["#/account", "Account settings", "Sign-in and sign-out", <UserIcon size={24} />],
  ["#/", "Browse markets", "Seaside Grocer, Tech, and more", <BagIcon size={24} />],
];

export default function BuyerDashboard() {
  const sessions = useAccountSessions();
  const [state, setState] = useState({ status: "loading", orders: [] });
  useEffect(() => {
    let cancelled = false;
    getBuyerOrders().then(
      ({ orders }) => !cancelled && setState({ status: "ready", orders }),
      (error) => !cancelled && setState({ status: error.status === 401 ? "unauthorized" : "error", orders: [] }),
    );
    return () => { cancelled = true; };
  }, []);
  const m = useMetrics(state.orders);
  const products = useCurrentProducts(state.orders);
  const orders = state.orders;

  return <section className="stack dash">
    <div className="dash-hero">
      <div>
        <PageHeading>{sessions.buyer ? `Hi, ${firstName(sessions.buyer.email)}` : "Your account"}</PageHeading>
        <p>{sessions.buyer ? `Signed in as ${sessions.buyer.email}` : "Your orders, addresses, and shopping in one place."}</p>
      </div>
      <div className="dash-hero-actions">
        <a className="btn btn-primary" href="#/">Shop</a>
        <a className="btn btn-secondary" href="#/buyer-orders">Your orders</a>
      </div>
    </div>

    {state.status === "loading" && <p className="note" role="status" aria-busy="true">Loading your account…</p>}
    {state.status === "unauthorized" && <SignInPrompt what="your dashboard" />}
    {state.status === "error" && <p className="message-error" role="alert">Unable to load your orders. Refresh to try again.</p>}

    {state.status === "ready" && <>
      <div className="dash-stats">
        <Stat icon={<BagIcon size={22} />} label="Spent, last 30 days" value={formatCents(m.spend)} caption={orders.length ? `${formatCents(m.lifetime)} all time` : null} />
        <Stat icon={<CheckIcon size={22} />} label="Orders, last 30 days" value={m.recentCount} caption={`${orders.length} all time`} />
        <Stat icon={<WavesIcon size={22} />} label="Being prepared" value={m.preparing} caption="Ordered, preparing, or packed" />
        <Stat icon={<TruckIcon size={22} />} label="Shipped or ready" value={m.onTheWay} caption="On the way or ready for pickup" />
      </div>

      {!orders.length ? <section className="dash-panel dash-welcome">
        <h2>Start your first order</h2>
        <p>Shop any market on the boardwalk by tapping, typing, or speaking. Orders you place while signed in show up here, with tracking and Buy it again.</p>
        <p><a className="btn btn-primary" href="#/">Browse markets</a></p>
      </section> : <div className="dash-columns">
        <div className="dash-side">
        <section className="dash-panel" aria-labelledby="recent-title">
          <div className="dash-panel-head"><h2 id="recent-title">Recent orders</h2><a href="#/buyer-orders">See all orders</a></div>
          <ul className="dash-orders">{orders.slice(0, 4).map((order) => <RecentOrder key={order.id} order={order} products={products} />)}</ul>
        </section>
        <section className="dash-panel" aria-labelledby="insights-title">
            <h2 id="insights-title">Your shopping</h2>
            <ul className="dash-insights">
              {m.favoriteMarket && <li><strong>{m.favoriteMarket[0]}</strong> is where you shop most ({m.favoriteMarket[1]} {m.favoriteMarket[1] === 1 ? "order" : "orders"}).</li>}
              {m.mostBought[0] && <li>Your most bought item is <strong>{m.mostBought[0].name}</strong> ({m.mostBought[0].units} total).</li>}
              {m.method && <li>You usually choose <strong>{m.method[0] === "PICKUP" ? "pickup" : "shipping"}</strong>.</li>}
            </ul>
          </section>
        </div>
        <div className="dash-side">
          <BuyAgain items={m.mostBought} products={products} />

        </div>
      </div>}

      <nav className="dash-tiles" aria-label="Account shortcuts">
        {TILES.map(([href, title, caption, icon]) => <a key={href} href={href} className="dash-tile">
          <span className="dash-tile-icon" aria-hidden="true">{icon}</span>
          <span><span className="dash-tile-title">{title}</span><span className="dash-tile-caption">{caption}</span></span>
        </a>)}
      </nav>
    </>}
  </section>;
}
