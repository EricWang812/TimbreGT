import { useEffect, useState } from "react";
import { useCart } from "../lib/cart.jsx";
import { getBuyerSession, getMarketOwnerSession, logoutBuyer, logoutMarketOwner } from "../lib/api.js";
import { BagIcon, MicIcon, UserIcon, WavesIcon } from "./Icons.jsx";
import { startHeaderVoiceShopping } from "./jump.js";

export default function SiteHeader({ onOpenCart, markets = [], selectedMarket, onSelectMarket }) {
  const { count } = useCart();
  const [account, setAccount] = useState({ buyer: null, owner: null });
  useEffect(() => {
    let active = true;
    Promise.all([getBuyerSession(), getMarketOwnerSession()]).then(([buyer, owner]) => {
      if (active) setAccount({ buyer: buyer.account, owner: owner.account });
    });
    return () => { active = false; };
  }, []);
  async function logout() {
    await Promise.allSettled([logoutBuyer(), logoutMarketOwner()]);
    setAccount({ buyer: null, owner: null });
  }
  const [marketSearchOpen, setMarketSearchOpen] = useState(false);
  const [marketQuery, setMarketQuery] = useState("");
  const marketMatches = markets.filter((market) => market.name.toLowerCase().includes(marketQuery.trim().toLowerCase()));
  function chooseMarket(market) {
    onSelectMarket?.(market.id);
    setMarketSearchOpen(false);
    setMarketQuery("");
  }
  // A5: the badge bumps only when the count goes up (never on first render,
  // never on a removal). Changing the key remounts the badge, which replays
  // the CSS animation without listening for animationend.
  const [badge, setBadge] = useState({ count, bumps: 0 });
  if (badge.count !== count) {
    setBadge({ count, bumps: count > badge.count ? badge.bumps + 1 : badge.bumps });
  }

  return (
    <header className="site-header" style={selectedMarket?.primaryColor ? { "--market-primary": selectedMarket.primaryColor } : undefined}>
      <div className="site-header-inner">
        <button type="button" className="brand market-switcher" onClick={() => setMarketSearchOpen(true)} aria-haspopup="dialog">
          {selectedMarket?.logoUrl ? <img className="market-brand-logo" src={selectedMarket.logoUrl} alt="" /> : <WavesIcon size={28} />}
          {selectedMarket?.name ?? "Choose a market"} <span aria-hidden="true">⌄</span>
        </button>
        <div className="header-actions">
          {/* A button, not a link: it moves focus on this page and never navigates.
              Below 600px it is icon-only; the text stays as its accessible name. */}
          <button type="button" className="header-voice" onClick={startHeaderVoiceShopping}>
            <MicIcon size={20} /> <span className="header-voice-text">Shop by voice</span>
          </button>
          <button type="button" className="btn btn-primary cart-button" onClick={onOpenCart} aria-haspopup="dialog">
            <BagIcon size={22} />
            Cart
            <span className="cart-count" key={badge.bumps} data-bump={badge.bumps > 0 ? "" : undefined}>{count}</span>
            <span className="visually-hidden">{count === 1 ? "item" : "items"}</span>
          </button>
          <details className="account-menu">
            <summary aria-label="Open account menu"><UserIcon size={21} /><span className="visually-hidden">Account</span></summary>
            <div className="account-menu-panel">
              {account.buyer && <><a href="#/buyer-dashboard">Buyer Dashboard</a><a href="#/buyer-orders">Orders</a><a href="#/addresses">Addresses</a></>}
              {account.owner && <a href="#/market-dashboard">Market Dashboard</a>}
              {(account.buyer || account.owner) ? <>
                <a href="#/account">Account Settings</a>
                <button type="button" onClick={logout}>Logout</button>
              </> : <p className="note">Sign in as a buyer or market owner through the available account API.</p>}
            </div>
          </details>
        </div>
      </div>
      {marketSearchOpen && <div className="market-search-backdrop" role="presentation" onMouseDown={() => setMarketSearchOpen(false)}>
        <section className="market-search" role="dialog" aria-modal="true" aria-labelledby="market-search-title" onMouseDown={(event) => event.stopPropagation()}>
          <h2 id="market-search-title">Choose a market</h2>
          <input autoFocus value={marketQuery} onChange={(event) => setMarketQuery(event.target.value)} placeholder="Search markets" aria-label="Search markets" />
          <ul>{marketMatches.map((market) => <li key={market.id}><button type="button" onClick={() => chooseMarket(market)}>{market.logoUrl ? <img className="market-search-logo" src={market.logoUrl} alt="" /> : <WavesIcon size={20} />} <span>{market.name}</span><small>{market.description ?? ""}</small></button></li>)}</ul>
          {!marketMatches.length && <p className="note">No markets match that search.</p>}
          <button type="button" className="btn btn-secondary" onClick={() => setMarketSearchOpen(false)}>Cancel</button>
        </section>
      </div>}
    </header>
  );
}
