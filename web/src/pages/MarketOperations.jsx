import { useEffect, useState } from "react";
import { getMarketOperations } from "../lib/api.js";
import { formatCents } from "../lib/money.js";
export default function MarketOperations({ marketId, revision }) {
  const [state, setState] = useState({ status: "loading" });
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true; setState({ status: "loading" });
    getMarketOperations(marketId).then((data) => { if (active) setState({ status: "ready", data }); }, () => { if (active) setState({ status: "error" }); });
    return () => { active = false; };
  }, [marketId, revision, retry]);
  if (state.status === "loading") return <p role="status">Loading operational metrics…</p>;
  if (state.status === "error") return <p role="alert">Unable to load operational metrics. <button onClick={() => setRetry((n) => n + 1)}>Try again</button></p>;
  const m = state.data;
  return <section><h3>Operations</h3><dl className="metric-grid">
    {[["Open preparation orders", m.openOrders], ["Fulfilling", m.fulfilling], ["Waiting to ship", m.waitingToShip], ["Ready for pickup", m.readyForPickup], ["Preparation completed", m.preparationCompleted], ["Average order value (all time)", m.averageOrderValueCents === null ? "Unavailable" : formatCents(m.averageOrderValueCents)]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
  </dl><p className="note">Open preparation includes Not Started, Fulfilling and Order Complete. Preparation completed includes orders already shipped or ready for pickup; delivery and pickup completion are not tracked.</p>
  {m.averageFulfillmentSeconds === null ? <p className="note">Average fulfillment time unavailable: no complete stage history yet.</p> : <p>Average fulfillment time: {Math.round(m.averageFulfillmentSeconds / 60)} minutes across {m.fulfillmentSampleCount} recorded transitions from Fulfilling to Order Complete.</p>}
  </section>;
}
