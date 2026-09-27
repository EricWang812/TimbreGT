import { useEffect, useRef, useState } from "react";
import { explainMarketInsights, getMarketInsights } from "../lib/api.js";

// Feature 13. The facts are the server's deterministic statements about this
// market's recorded orders. The optional explanation only rewords facts the
// server chose to send; the server discards wording with any other number.
export default function MarketInsights({ marketId, revision }) {
  const [state, setState] = useState({ status: "loading" });
  const [retry, setRetry] = useState(0);
  const [explanation, setExplanation] = useState({ status: "idle" });
  const request = useRef(0);
  useEffect(() => {
    let active = true;
    request.current += 1;  // a stale explanation never lands on new facts
    setState({ status: "loading" });
    setExplanation({ status: "idle" });
    getMarketInsights(marketId).then(
      (data) => { if (active) setState({ status: "ready", data }); },
      () => { if (active) setState({ status: "error" }); },
    );
    return () => { active = false; };
  }, [marketId, revision, retry]);

  async function explain() {
    const id = ++request.current;
    setExplanation({ status: "loading" });
    try {
      const data = await explainMarketInsights(marketId);
      if (id === request.current) setExplanation({ status: "ready", data });
    } catch (error) {
      if (id !== request.current) return;
      setExplanation({ status: "error", message: error.status === 409
        ? "There is not enough order history to explain yet."
        : error.status === 503 && /not configured/i.test(error.message)
          ? "AI explanations are not configured on the merchant server."
          : "The AI explanation is unavailable right now. The facts above are still accurate." });
    }
  }

  if (state.status === "loading") return <p role="status" aria-busy="true">Loading insights…</p>;
  if (state.status === "error") return <p className="message-error" role="alert">Unable to load insights. <button type="button" className="btn btn-secondary" onClick={() => setRetry((n) => n + 1)}>Try again</button></p>;
  const { facts, aiAvailable } = state.data;
  const byId = Object.fromEntries(facts.map((f) => [f.id, f]));
  return <section className="stack" aria-labelledby="insights-title">
    <h3 id="insights-title">Insights</h3>
    <p className="note">Computed from this market's recorded orders. Each statement appears only when there is enough history to support it. Nothing here changes an order.</p>
    {!facts.length ? <p>No insights yet. They appear as orders are recorded and move through fulfillment.</p> : <>
      <ul className="insight-list">{facts.map((fact) => <li key={fact.id} className={`insight insight-${fact.tone}`}>
        <span className="insight-label">{fact.tone === "attention" ? "Needs action" : "Pattern"}</span>
        <p>{fact.text}</p>
      </li>)}</ul>
      {aiAvailable ? <div className="stack">
        <p><button type="button" className="btn btn-secondary" disabled={explanation.status === "loading"} onClick={explain}>
          {explanation.status === "loading" ? "Writing explanation…" : explanation.status === "ready" ? "Explain again" : "Explain in plain language"}
        </button></p>
        <div aria-live="polite">
          {explanation.status === "error" && <p className="message-error">{explanation.message}</p>}
          {explanation.status === "ready" && <section className="insight-explanation stack" aria-label="Plain-language explanation">
            {explanation.data.headline && <p><strong>{explanation.data.headline}</strong></p>}
            <ul>{explanation.data.highlights.map((h) => <li key={h.factId}>{h.text} <span className="note">(from: {byId[h.factId]?.text ?? "a fact above"})</span></li>)}</ul>
            <p className="note">Worded by AI ({explanation.data.model}) from the facts above only. Numbers were checked against those facts.</p>
          </section>}
        </div>
      </div> : <p className="note">Plain-language AI explanations are off because the merchant server has no OpenAI key. The facts above do not need it.</p>}
    </>}
  </section>;
}
