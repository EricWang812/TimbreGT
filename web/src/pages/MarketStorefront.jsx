import { useEffect, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { getMarketBranding } from "../lib/api.js";

export default function MarketStorefront({ marketId }) {
  const [state, setState] = useState({ status: "loading", market: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", market: null });
    getMarketBranding(marketId).then(
      (market) => {
        if (!cancelled) {
          document.title = `${market.name}, Timbre`;
          setState({ status: "ready", market });
        }
      },
      (error) => {
        console.error("market branding failed to load", error);
        if (!cancelled) setState({ status: "error", market: null });
      },
    );
    return () => { cancelled = true; };
  }, [marketId]);

  if (state.status === "loading") {
    return <div className="stack"><p className="note" aria-busy="true">Loading market…</p></div>;
  }
  if (state.status === "error") {
    return (
      <div className="stack">
        <PageHeading>Market unavailable</PageHeading>
        <p className="message-error" role="alert">This market could not be loaded.</p>
      </div>
    );
  }

  const market = state.market;
  return (
    <section
      className="market-storefront-brand"
      style={{ "--market-primary": market.primaryColor }}
      aria-labelledby="market-storefront-name"
    >
      <div className="market-storefront-logo" aria-hidden="true">
        {market.logoUrl
          ? <img src={market.logoUrl} alt="" />
          : <span>{market.logoPlaceholder}</span>}
      </div>
      <div>
        <p className="eyebrow">Market storefront</p>
        <PageHeading id="market-storefront-name">{market.name}</PageHeading>
        <p className="note">Products from this market will appear here when its catalog is ready.</p>
      </div>
    </section>
  );
}
