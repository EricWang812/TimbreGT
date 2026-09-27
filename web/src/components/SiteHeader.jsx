import { useEffect, useRef, useState } from "react";
import { useCart } from "../lib/cart.jsx";
import { flash, notifyAccountChanged, signInHref, useAccountSessions } from "../lib/account.js";
import { navigate } from "../lib/router.js";
import { logoutBuyer, logoutMarketOwner } from "../lib/api.js";
import { BagIcon, MicIcon, UserIcon, WavesIcon } from "./Icons.jsx";
import { startHeaderVoiceShopping } from "./jump.js";

export default function SiteHeader({ onOpenCart, markets = [], selectedMarket, onSelectMarket }) {
  const { count } = useCart();
  const account = useAccountSessions();
  const menu = useRef(null);
  // The header outlives navigation, so the menu closes itself on a route change.
  useEffect(() => {
    const close = () => { if (menu.current) menu.current.open = false; };
    window.addEventListener("hashchange", close);
    return () => window.removeEventListener("hashchange", close);
  }, []);
  function closeMenuOnEscape(event) {
    if (event.key !== "Escape" || !menu.current?.open) return;
    menu.current.open = false;
    menu.current.querySelector("summary").focus();
  }
  // Signing out leaves any account page (it would only show "sign in" now)
  // and says so, instead of silently changing the menu.
  async function logout() {
    const results = await Promise.allSettled([logoutBuyer(), logoutMarketOwner()]);
    notifyAccountChanged();
    if (menu.current) menu.current.open = false;
    if (results.some((r) => r.status === "rejected")) {
      flash("Sign-out could not reach the store. Try again.");
      return;
    }
    navigate("/");
    flash("You are signed out.");
  }
  const [marketSearchOpen, setMarketSearchOpen] = useState(false);
  const [marketQuery, setMarketQuery] = useState("");
  const marketMatches = markets.filter((market) => market.name.toLowerCase().includes(marketQuery.trim().toLowerCase()));
  const switcherButton = useRef(null);
  function closeMarketSearch() {
    setMarketSearchOpen(false);
    setMarketQuery("");
    setTimeout(() => switcherButton.current?.focus());   // back to the control that opened it
  }
  function chooseMarket(market) {
    onSelectMarket?.(market.id);
    closeMarketSearch();
  }
  // A modal dialog: Escape closes it, and Tab stays inside it.
  function dialogKeys(event) {
    if (event.key === "Escape") { event.preventDefault(); closeMarketSearch(); return; }
    if (event.key !== "Tab") return;
    const focusable = [...event.currentTarget.querySelectorAll("input, button")];
    const first = focusable[0], last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
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
        <button ref={switcherButton} type="button" className="brand market-switcher" onClick={() => setMarketSearchOpen(true)} aria-haspopup="dialog">
          {selectedMarket?.logoUrl ? <img className="market-brand-logo" src={selectedMarket.logoUrl} alt="" /> : <span className="brand-mark"><WavesIcon size={28} /></span>}
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
            <span className="cart-label">Cart</span>
            <span className="cart-count" key={badge.bumps} data-bump={badge.bumps > 0 ? "" : undefined}>{count}</span>
            <span className="visually-hidden">{count === 1 ? "item" : "items"}</span>
          </button>
          <details className="account-menu" ref={menu} onKeyDown={closeMenuOnEscape}>
            <summary aria-label={account.buyer || account.owner ? "Account menu, signed in" : "Account menu"}><UserIcon size={21} /></summary>
            <div className="account-menu-panel">
              {(account.buyer || account.owner) && <p className="note account-menu-email">{(account.buyer ?? account.owner).email}</p>}
              {account.buyer && <><a href="#/buyer-dashboard">Buyer Dashboard</a><a href="#/buyer-orders">Orders</a><a href="#/addresses">Addresses</a></>}
              {account.owner && <a href="#/market-dashboard">Market Dashboard</a>}
              {(account.buyer || account.owner) ? <>
                <a href="#/account">Account Settings</a>
                {!(account.buyer && account.owner) && <a href={signInHref(account.buyer ? "owner" : "buyer")}>{account.buyer ? "Sign in as market owner" : "Sign in as buyer"}</a>}
                <button type="button" onClick={logout}>Sign out</button>
              </> : <>
                {account.status === "error" && <p className="note">Account status is unavailable right now.</p>}
                <a href={signInHref("buyer")}>Sign in</a>
                <a href={signInHref("owner")}>Market owner sign in</a>
              </>}
            </div>
          </details>
        </div>
      </div>
      {marketSearchOpen && <div className="market-search-backdrop" role="presentation" onMouseDown={closeMarketSearch}>
        <section className="market-search" role="dialog" aria-modal="true" aria-labelledby="market-search-title" onMouseDown={(event) => event.stopPropagation()} onKeyDown={dialogKeys}>
          <h2 id="market-search-title">Choose a market</h2>
          <input autoFocus value={marketQuery} onChange={(event) => setMarketQuery(event.target.value)} placeholder="Search markets" aria-label="Search markets" />
          <ul>{marketMatches.map((market) => <li key={market.id}><button type="button" onClick={() => chooseMarket(market)}>{market.logoUrl ? <img className="market-search-logo" src={market.logoUrl} alt="" /> : <WavesIcon size={20} />} <span>{market.name}</span><small>{market.description ?? ""}</small></button></li>)}</ul>
          {!marketMatches.length && <p className="note">No markets match that search.</p>}
          <button type="button" className="btn btn-secondary" onClick={closeMarketSearch}>Cancel</button>
        </section>
      </div>}
    </header>
  );
}
