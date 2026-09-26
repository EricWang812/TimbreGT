import { useEffect, useState } from "react";
import { getMarketAnalytics } from "../lib/api.js";
import { formatCents } from "../lib/money.js";
export default function MarketAnalytics({ marketId }) {
  const [period, setPeriod] = useState("30D");
  const [state, setState] = useState({ status: "loading" });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setState({ status: "loading" });
    getMarketAnalytics(marketId, period).then((data) => { if (active) setState({ status: "ready", data }); }, () => { if (active) setState({ status: "error" }); });
    return () => { active = false; };
  }, [marketId, period, retry]);
  const data = state.data;
  return <section className="stack">
    <div className="management-actions" aria-label="Analytics period">{["7D", "30D", "1Y"].map((p) => <button className="chip" key={p} aria-pressed={p === period} onClick={() => setPeriod(p)}>{p}</button>)}</div>
    <p className="note">Rolling periods in UTC; 1Y is 365 days. Revenue is the recorded paid order total, not profit. Product revenue uses purchase-time item prices.</p>
    {state.status === "loading" && <p role="status">Loading analytics…</p>}
    {state.status === "error" && <p role="alert">Unable to load analytics. <button onClick={() => setRetry((n) => n + 1)}>Try again</button></p>}
    {data && <>
      <dl className="metric-grid"><div><dt>Revenue</dt><dd>{formatCents(data.revenueCents)}</dd></div><div><dt>Orders</dt><dd>{data.orderCount}</dd></div><div><dt>Average order value</dt><dd>{data.averageOrderValueCents === null ? "Unavailable" : formatCents(data.averageOrderValueCents)}</dd></div><div><dt>Units sold</dt><dd>{data.unitsSold}</dd></div></dl>
      {data.revenueChangePercent !== null ? <p>{data.revenueChangePercent > 0 ? "+" : ""}{data.revenueChangePercent}% revenue vs previous {data.days} days.</p> : <p className="note">No percentage comparison: the previous period has no revenue.</p>}
      {!!data.excludedUndatedOrders && <p role="status">{data.excludedUndatedOrders} orders have no usable timestamp and are excluded from period totals.</p>}
      {!data.orderCount ? <p>No sales data for this period.</p> : <>
        <h3>Top products by units sold</h3><div className="table-scroll"><table className="management-table"><thead><tr><th>Product</th><th>Units sold</th><th>Product revenue</th></tr></thead><tbody>{data.topProducts.map((p) => <tr key={p.productId}><td>{p.name}</td><td>{p.units}</td><td>{formatCents(p.revenueCents)}</td></tr>)}</tbody></table></div>
        <details><summary>Daily revenue (UTC)</summary><div className="table-scroll"><table className="management-table"><thead><tr><th>Date</th><th>Revenue</th></tr></thead><tbody>{data.dailyRevenue.map((day) => <tr key={day.date}><td>{day.date}</td><td>{formatCents(day.revenueCents)}</td></tr>)}</tbody></table></div></details>
      </>}
    </>}
  </section>;
}
