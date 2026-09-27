import { useEffect, useRef, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { signInHref } from "../lib/account.js";
import { createMarket, getMarketOrders, getMarketOwnerAccount, getOwnedMarkets, updateMarketOrderStatus } from "../lib/api.js";
import { formatCents } from "../lib/money.js";
import { ORDER_STAGES, attention, elapsed, fulfillmentLabel, orderLink, statusLabel } from "../lib/marketOrders.js";
import MarketAnalytics from "./MarketAnalytics.jsx";
import MarketFulfillment from "./MarketFulfillment.jsx";
import MarketProducts from "./MarketProducts.jsx";
import MarketInsights from "./MarketInsights.jsx";
import MarketOperations from "./MarketOperations.jsx";
import MarketOrders from "./MarketOrders.jsx";
import MarketOrderDetails from "./MarketOrderDetails.jsx";

// page -> [hash route prefix, nav label, heading]
const PAGES = {
  overview: ["market-dashboard", "Overview", "Market Overview"],
  orders: ["market-orders", "Orders", "Market Orders"],
  products: ["market-products", "Products", "Market Products"],
  delivery: ["market-delivery", "Delivery", "Delivery Settings"],
  analytics: ["market-analytics", "Analytics", "Market Analytics"],
  insights: ["market-insights", "Insights", "Market Insights"],
};

function CreateMarketForm({ onCreated }) {
  const [name, setName] = useState("");
  const [state, setState] = useState({ status: "idle" });
  async function submit(event) {
    event.preventDefault();
    if (state.status === "saving") return;
    setState({ status: "saving" });
    try {
      const market = await createMarket(name);
      onCreated(market);
    } catch (error) {
      setState({ status: "error", message: error.status === 422 ? "Enter a market name." : "The market could not be created. Try again." });
    }
  }
  return <form className="auth-form stack" onSubmit={submit}>
    <h2>Create your first market</h2>
    <p className="note">You can add products, pickup, and shipping settings after it exists.</p>
    <label className="form-field">Market name<input required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></label>
    {state.status === "error" && <p className="message-error" role="alert">{state.message}</p>}
    <button type="submit" className="btn btn-primary" disabled={state.status === "saving"}>{state.status === "saving" ? "Creating…" : "Create market"}</button>
  </form>;
}

export default function MarketDashboard({ marketId, orderId, page = "overview" }) {
  const [account, setAccount] = useState({ status: "loading", markets: [] });
  const [accountRetry, setAccountRetry] = useState(0);
  const [board, setBoard] = useState({ status: "loading", orders: [] });
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const mutation = useRef(false);
  useEffect(() => {
    let active = true;
    setAccount({ status: "loading", markets: [] });
    async function load() {
      try {
        const owner = await getMarketOwnerAccount();
        const markets = await getOwnedMarkets();
        if (active) setAccount({ status: "ready", owner, markets });
      } catch (error) {
        if (active) setAccount({ status: error.status === 401 ? "unauthorized" : "error", markets: [] });
      }
    }
    load();
    return () => { active = false; };
  }, [accountRetry]);
  const market = account.markets.find((m) => m.id === marketId) ?? (!marketId ? account.markets[0] : null);
  useEffect(() => {
    if (!market) return;
    let active = true;
    setBoard({ status: "loading", orders: [] });
    getMarketOrders(market.id).then(
      (data) => { if (active) setBoard({ status: "ready", orders: data.orders }); },
      () => { if (active) setBoard({ status: "error", orders: [] }); },
    );
    return () => { active = false; };
  }, [market?.id, reload]);
  async function move(id, status) {
    if (mutation.current) return;
    mutation.current = true; setBusy(true); setMessage(null);
    try {
      await updateMarketOrderStatus(market.id, id, status);
      setMessage({ text: `Order moved to ${statusLabel(status)}.` });
      setReload((n) => n + 1);
    } catch {
      setMessage({ error: true, text: "The order could not move. Refresh to see its current status and try again." });
    } finally { mutation.current = false; setBusy(false); }
  }
  function created(newMarket) {
    setAccount((a) => ({ ...a, markets: [...a.markets, newMarket] }));
    window.location.hash = `/market-products/${newMarket.id}`;   // a new market starts by adding products
  }
  const [routePrefix, , heading] = PAGES[page] ?? PAGES.overview;
  const selectedOrder = board.orders.find((order) => order.id === orderId);
  return <section className="stack market-management">
    <PageHeading>{orderId ? "Order details" : heading}</PageHeading>
    <a href="#/">Back to storefront</a>
    {account.status === "loading" && <p role="status" aria-busy="true">Checking market account…</p>}
    {account.status === "unauthorized" && <p role="alert">Sign in as a market owner to access this dashboard. <a href={signInHref("owner")}>Sign in or create a market owner account</a></p>}
    {account.status === "error" && <p className="message-error" role="alert">Unable to load your market account. <button type="button" className="btn btn-secondary" onClick={() => setAccountRetry((n) => n + 1)}>Try again</button></p>}
    {account.status === "ready" && <>
      {!account.markets.length ? <><p className="note">Signed in as <span className="break-anywhere">{account.owner.email}</span></p><CreateMarketForm onCreated={created} /></> : <>
        <div className="seller-toolbar">
        <label className="management-select">Managed market<select value={market?.id ?? ""} disabled={busy} onChange={(e) => { window.location.hash = `/${routePrefix}/${e.target.value}`; }}><option value="" disabled>Choose a market</option>{account.markets.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        <p className="note">Signed in as <span className="break-anywhere">{account.owner.email}</span></p>
        </div>
        {!market ? <p role="alert">This market is unavailable for this account.</p> : <>
          <nav className="management-actions management-nav" aria-label="Market management">{Object.entries(PAGES).map(([key, [prefix, label]]) =>
            <a key={key} href={`#/${prefix}/${market.id}`} aria-current={key === page && !orderId ? "page" : undefined}>{label}</a>)}</nav>
          <h2>{market.name}</h2>
          {page === "products" && !orderId ? <MarketProducts key={market.id} market={market} />
            : page === "delivery" && !orderId ? <MarketFulfillment key={market.id} market={market} /> : <>
          {(page === "overview" || page === "orders" || orderId) && <p><button type="button" className="btn btn-secondary" disabled={busy || board.status === "loading"} onClick={() => setReload((n) => n + 1)}>Refresh orders</button></p>}
          {message && <p className={message.error ? "message-error" : undefined} role={message.error ? "alert" : "status"}>{message.text}</p>}
          {board.status === "loading" && <p role="status" aria-busy="true">Loading orders…</p>}
          {board.status === "error" && <p className="message-error" role="alert">Unable to load market orders. Use Refresh orders to try again.</p>}
          {board.status === "ready" && (orderId ? (selectedOrder ? <MarketOrderDetails order={selectedOrder} marketId={market.id} onMove={move} busy={busy} /> : <p role="alert">Order not found in this market.</p>)
            : page === "analytics" ? <MarketAnalytics marketId={market.id} />
            : page === "insights" ? <MarketInsights marketId={market.id} revision={reload} />
            : page === "orders" ? <MarketOrders orders={board.orders} marketId={market.id} /> : <>
            <MarketOperations marketId={market.id} revision={reload} />
            {!board.orders.length && <p>No orders yet. New paid orders appear here in Not Started.</p>}
            <div className="order-board">{ORDER_STAGES.map(([key, label]) => {
              const orders = board.orders.filter((order) => order.status === key);
              return <section key={key} className="order-column"><h3>{label} <span className="note">({orders.length})</span></h3>
                {!orders.length ? <p className="note">No orders</p> : <ul className="order-cards">{orders.map((order) => <li key={order.id} className="order-card">
                  <a href={orderLink(market.id, order.id)}>Order {order.id.slice(0, 8)}</a>
                  <strong>{formatCents(order.totalCents)}</strong>
                  <p>{order.items.reduce((n, item) => n + item.amount, 0)} items · {fulfillmentLabel(order)}</p>
                  <p className="note">Order age: {elapsed(order.createdAt)}</p>
                  {attention(order) && <p className="order-attention">{attention(order)}</p>}
                  {order.allowedTransitions?.map((status) => <button type="button" className="btn btn-secondary" key={status} disabled={busy} onClick={() => move(order.id, status)}>Move to {statusLabel(status)}</button>)}
                </li>)}</ul>}
              </section>;
            })}</div>
          </>)}
          </>}
        </>}
      </>}
    </>}
  </section>;
}
