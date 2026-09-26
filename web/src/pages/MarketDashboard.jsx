import { useEffect, useRef, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { getMarketOrders, getMarketOwnerAccount, getOwnedMarkets, updateMarketOrderStatus } from "../lib/api.js";
import { formatCents } from "../lib/money.js";
import { ORDER_STAGES, attention, elapsed, fulfillmentLabel, orderLink, statusLabel } from "../lib/marketOrders.js";
import MarketAnalytics from "./MarketAnalytics.jsx";
import MarketOperations from "./MarketOperations.jsx";
import MarketOrders from "./MarketOrders.jsx";
import MarketOrderDetails from "./MarketOrderDetails.jsx";

export default function MarketDashboard({ marketId, orderId, page = "overview" }) {
  const [account, setAccount] = useState({ status: "loading", markets: [] });
  const [board, setBoard] = useState({ status: "loading", orders: [] });
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const mutation = useRef(false);
  useEffect(() => {
    let active = true;
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
  }, []);
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
  const selectedOrder = board.orders.find((order) => order.id === orderId);
  return <section className="stack market-management">
    <PageHeading>{orderId ? "Order details" : page === "orders" ? "Market Orders" : page === "analytics" ? "Market Analytics" : "Market Overview"}</PageHeading>
    <a href="#/">Back to storefront</a>
    {account.status === "loading" && <p role="status">Checking market account…</p>}
    {account.status === "unauthorized" && <p role="alert">Sign in as a market owner to access this dashboard.</p>}
    {account.status === "error" && <p role="alert">Unable to load your market account. <button onClick={() => window.location.reload()}>Try again</button></p>}
    {account.status === "ready" && <>
      <p className="note">Signed in as {account.owner.email}</p>
      {!account.markets.length ? <p>No markets available for this account.</p> : <>
        <label className="management-select">Managed market<select value={market?.id ?? ""} disabled={busy} onChange={(e) => { window.location.hash = `/${page === "orders" ? "market-orders" : page === "analytics" ? "market-analytics" : "market-dashboard"}/${e.target.value}`; }}><option value="" disabled>Choose a market</option>{account.markets.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></label>
        {!market ? <p role="alert">This market is unavailable for this account.</p> : <>
          <nav className="management-actions" aria-label="Market management"><a href={`#/market-dashboard/${market.id}`}>Overview</a><a href={`#/market-orders/${market.id}`}>Orders</a><a href={`#/market-analytics/${market.id}`}>Analytics</a></nav>
          <h2>{market.name}</h2>
          <button className="btn btn-secondary" disabled={busy || board.status === "loading"} onClick={() => setReload((n) => n + 1)}>Refresh orders</button>
          {message && <p role={message.error ? "alert" : "status"}>{message.text}</p>}
          {board.status === "loading" && <p role="status" aria-busy="true">Loading orders…</p>}
          {board.status === "error" && <p className="message-error" role="alert">Unable to load market orders. Use Refresh orders to try again.</p>}
          {board.status === "ready" && (orderId ? (selectedOrder ? <MarketOrderDetails order={selectedOrder} marketId={market.id} onMove={move} busy={busy} /> : <p role="alert">Order not found in this market.</p>) : page === "analytics" ? <MarketAnalytics marketId={market.id} /> : page === "orders" ? <MarketOrders orders={board.orders} marketId={market.id} /> : <>
            <MarketOperations marketId={market.id} revision={reload} />
            {!board.orders.length && <p>No orders yet.</p>}
            <div className="order-board">{ORDER_STAGES.map(([key, label]) => {
              const orders = board.orders.filter((order) => order.status === key);
              return <section key={key} className="order-column"><h3>{label} <span className="note">({orders.length})</span></h3>
                {!orders.length ? <p className="note">No orders</p> : <ul className="order-cards">{orders.map((order) => <li key={order.id} className="order-card">
                  <a href={orderLink(market.id, order.id)}>Order {order.id.slice(0, 8)}</a>
                  <strong>{formatCents(order.totalCents)}</strong>
                  <p>{order.items.reduce((n, item) => n + item.amount, 0)} items · {fulfillmentLabel(order)}</p>
                  <p className="note">Order age: {elapsed(order.createdAt)}</p>
                  {attention(order) && <p className="order-attention">{attention(order)}</p>}
                  {order.allowedTransitions?.map((status) => <button className="btn btn-secondary" key={status} disabled={busy} onClick={() => move(order.id, status)}>Move to {statusLabel(status)}</button>)}
                </li>)}</ul>}
              </section>;
            })}</div>
          </>)}
        </>}
      </>}
    </>}
  </section>;
}
