import { useCallback, useEffect, useRef, useState } from "react";
import CartDrawer from "./components/CartDrawer.jsx";
import EnrollPage from "./issuer/EnrollPage.jsx";
import SiteHeader from "./components/SiteHeader.jsx";
import { CheckIcon, CloseIcon } from "./components/Icons.jsx";
import { AnnouncerProvider } from "./lib/announce.jsx";
import { getCartProducts, getStorefrontMarkets, getStorefrontProducts } from "./lib/api.js";
import { CartProvider, useCart } from "./lib/cart.jsx";
import { useRoute } from "./lib/router.js";
import Baseline from "./pages/Baseline.jsx";
import Checkout from "./pages/Checkout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Receipt from "./pages/Receipt.jsx";
import Shop from "./pages/Shop.jsx";
import MarketStorefront from "./pages/MarketStorefront.jsx";
import BuyerDashboard from "./pages/BuyerDashboard.jsx";
import { BuyerOrderDetails, BuyerOrders } from "./pages/BuyerOrders.jsx";
import MarketDashboard from "./pages/MarketDashboard.jsx";
import SignIn from "./pages/SignIn.jsx";
import Account from "./pages/Account.jsx";
import Addresses from "./pages/Addresses.jsx";

function useCatalog() {
  const [state, setState] = useState({ status: "loading", products: [], byId: {} });
  const latest = useRef(0);  // only the newest request may update state
  const known = useRef({});

  const load = useCallback((marketId) => {
    if (!marketId) return Promise.reject(new Error("A market is required to load its catalog."));
    const request = ++latest.current;
    setState((s) => ({ ...s, status: s.market ? "ready" : "loading", switching: true, error: null }));
    return getStorefrontProducts(marketId).then(
      ({ market, products }) => {
        if (request !== latest.current) return null;
        setState({
        status: "ready", switching: false, error: null,
        market,
        products,
        byId: Object.assign(known.current, Object.fromEntries(products.map((p) => [p.id, p]))),
        });
        return market;
      },
      (err) => {
        console.error("catalog failed to load", err);
        if (request === latest.current) setState((s) => ({ ...s, status: s.market ? "ready" : "error", switching: false, error: "Unable to switch markets. Please try again." }));
        throw err;
      },
    );
  }, []);
  return { ...state, reload: load };
}

function useStorefrontMarkets() {
  const [store, setStore] = useState({ status: "loading", markets: [] });
  useEffect(() => { getStorefrontMarkets().then((data) => setStore({ status: "ready", markets: data.markets }), () => setStore({ status: "error", markets: [] })); }, []);
  return store;
}

// WCAG 2.4.2: every view has its own title, announced when it changes.
const TITLES = {
  baseline: "Two ways to check a voice, Timbre demo",
  dashboard: "Voice changes over time, Timbre demo",
  market: "Market storefront, Timbre",
  "bank-enroll": "Set up voice approval, your bank (demo)",
  "sign-in": "Sign in, Timbre",
  account: "Account settings, Timbre",
  addresses: "Addresses, Timbre",
  "buyer-dashboard": "Buyer Dashboard, Timbre",
  "buyer-orders": "Orders, Timbre",
  "buyer-order": "Order details, Timbre",
  "market-dashboard": "Market Overview, Timbre",
  "market-orders": "Market Orders, Timbre",
  "market-analytics": "Market Analytics, Timbre",
  "market-insights": "Market Insights, Timbre",
  "market-products": "Market Products, Timbre",
  "market-delivery": "Delivery Settings, Timbre",
};

// Sign-in and sign-out confirmations (lib/account.js flash()). Lives outside
// <main>, which remounts per route, so it survives the redirect it follows.
const FLASH_MS = 5000;
function Flash() {
  const [message, setMessage] = useState(null);
  useEffect(() => {
    let timer;
    const show = (event) => {
      setMessage(event.detail);
      clearTimeout(timer);
      timer = setTimeout(() => setMessage(null), FLASH_MS);
    };
    window.addEventListener("timbre:flash", show);
    return () => { window.removeEventListener("timbre:flash", show); clearTimeout(timer); };
  }, []);
  return <div className="flash-region" role="status" aria-live="polite">
    {message && <div className="flash">
      <CheckIcon size={18} />
      <span>{message}</span>
      <button type="button" className="flash-close" onClick={() => setMessage(null)} aria-label="Dismiss message"><CloseIcon size={18} /></button>
    </div>}
  </div>;
}

function Shell() {
  const cart = useCart();
  const [cartProducts, setCartProducts] = useState({});
  const [cartError, setCartError] = useState(null);
  const cartIds = cart.lines.map((line) => line.productId).sort().join(",");
  useEffect(() => {
    let active = true;
    setCartError(null);
    if (!cartIds) return;
    getCartProducts(cartIds.split(",")).then(({ products }) => {
      if (active) setCartProducts(Object.fromEntries(products.map((p) => [p.id, p])));
    }, () => { if (active) setCartError("Unable to load current cart products. Try refreshing."); });
    return () => { active = false; };
  }, [cartIds]);
  const route = useRoute();
  const store = useStorefrontMarkets();
  const [selectedMarketId, setSelectedMarketId] = useState(() => {
    try { return localStorage.getItem("timbre.selectedMarketId") ?? null; } catch { return null; }
  });
  const catalog = useCatalog();
  const selectedMarket = catalog.market ?? null;
  const loadStarted = useRef(false);
  useEffect(() => {
    if (loadStarted.current || !store.markets.length) return;
    loadStarted.current = true;
    const initial = store.markets.some((market) => market.id === selectedMarketId)
      ? selectedMarketId : store.markets[0].id;
    catalog.reload(initial).then((market) => {
      if (!market) return;
      setSelectedMarketId(market.id);
      try { localStorage.setItem("timbre.selectedMarketId", market.id); } catch { /* optional convenience only */ }
    }).catch(() => { /* the catalog hook retains the valid market and exposes its error state */ });
  }, [store.markets, selectedMarketId, catalog]);
  async function selectMarket(id) {
    if (!store.markets.some((market) => market.id === id)) return;
    try {
      const market = await catalog.reload(id);
      if (!market) return;
      setSelectedMarketId(market.id);
      try { localStorage.setItem("timbre.selectedMarketId", market.id); } catch { /* optional convenience only */ }
    } catch { /* the catalog hook retains the valid market and exposes its error state */ }
  }
  useEffect(() => {
    const marketName = selectedMarket?.name ?? "Timbre";
    const pageTitle = route.name === "shop" ? marketName
      : route.name === "checkout" ? `Checkout, ${marketName}`
        : route.name === "receipt" ? `Receipt, ${marketName}`
          : TITLES[route.name] ?? marketName;
    document.title = pageTitle;
  }, [route.name, selectedMarket]);
  const [cartOpen, setCartOpen] = useState(false);

  // A plain href="#main" would be read as a route by the hash router.
  function skipToMain(event) {
    event.preventDefault();
    document.getElementById("main-content").focus();
  }

  // The bank's app is a different party: no store header, cart, or footer.
  if (route.name === "bank-enroll") {
    return (
      <>
        <a className="skip-link" href="#main-content" onClick={skipToMain}>Skip to main content</a>
        <EnrollPage userId={route.userId} />
      </>
    );
  }

  return (
    <>
      <a className="skip-link" href="#main-content" onClick={skipToMain}>Skip to main content</a>
      {cartError && <p className="message-error" role="alert">{cartError}</p>}
      <SiteHeader onOpenCart={() => setCartOpen(true)} markets={store.markets} selectedMarket={selectedMarket} onSelectMarket={selectMarket} />
      {/* key: each route mounts fresh, so the .route-enter fade (styles.css) replays on navigation. */}
      <main id="main-content" tabIndex={-1} key={`${route.name}:${route.marketId ?? ""}:${route.orderId ?? ""}:${route.role ?? ""}`} className="route-enter">
        {route.name === "shop" && <Shop key={selectedMarket?.id ?? "none"} catalog={{ ...catalog, status: store.status === "error" ? "error" : store.status === "ready" && !store.markets.length ? "ready" : catalog.status, reload: () => selectMarket(selectedMarket?.id ?? store.markets[0]?.id) }} onOpenCart={() => setCartOpen(true)} selectedMarketId={selectedMarket?.id ?? null} selectedMarket={selectedMarket} onSelectMarket={selectMarket} />}
        {route.name === "checkout" && <Checkout products={{ ...catalog.byId, ...cartProducts }} />}
        {route.name === "baseline" && <Baseline />}
        {route.name === "dashboard" && <Dashboard />}
        {route.name === "buyer-dashboard" && <BuyerDashboard />}
        {route.name === "buyer-orders" && <BuyerOrders />}
        {route.name === "buyer-order" && <BuyerOrderDetails orderId={route.orderId} />}
        {route.name === "market-analytics" && <MarketDashboard marketId={route.marketId} page="analytics" />}
        {route.name === "market-orders" && <MarketDashboard marketId={route.marketId} page="orders" />}
        {route.name === "market-insights" && <MarketDashboard marketId={route.marketId} page="insights" />}
        {route.name === "market-products" && <MarketDashboard marketId={route.marketId} page="products" />}
        {route.name === "market-delivery" && <MarketDashboard marketId={route.marketId} page="delivery" />}
        {route.name === "sign-in" && <SignIn key={route.role} role={route.role} next={route.next} />}
        {route.name === "account" && <Account />}
        {route.name === "addresses" && <Addresses />}
        {route.name === "market-dashboard" && <MarketDashboard marketId={route.marketId} orderId={route.orderId} />}
        {route.name === "market" && <MarketStorefront marketId={route.marketId} />}
        {route.name === "receipt" && <Receipt key={route.instructionId} instructionId={route.instructionId} products={{ ...catalog.byId, ...cartProducts }} />}
      </main>
      <footer className="site-footer">
        <p className="note">
          Timbre connects you with your selected market. Product photos: contributors to{" "}
          <a href="https://world.openfoodfacts.org" target="_blank" rel="noopener noreferrer">Open Food Facts (opens a new tab)</a>,{" "}
          <a href="https://world.openbeautyfacts.org" target="_blank" rel="noopener noreferrer">Open Beauty Facts (opens a new tab)</a>,{" "}
          <a href="https://world.openpetfoodfacts.org" target="_blank" rel="noopener noreferrer">Open Pet Food Facts (opens a new tab)</a>, and{" "}
          <a href="https://world.openproductsfacts.org" target="_blank" rel="noopener noreferrer">Open Products Facts (opens a new tab)</a>,{" "}
          <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 3.0 (opens a new tab)</a>.
        </p>
        <p className="note"><a href="#/bank/enroll">Set up voice approval at your bank (demo)</a></p>
        <p className="note"><a href="#/baseline">Why transcription is the wrong test (demo comparison)</a></p>
        <p className="note"><a href="#/dashboard">Voice changes over time (adaptation demo)</a></p>
      </footer>
      <Flash />
      <CartDrawer open={cartOpen} onClose={() => setCartOpen(false)} products={{ ...catalog.byId, ...cartProducts }} />
    </>
  );
}

export default function App() {
  return (
    <AnnouncerProvider>
      <CartProvider>
        <Shell />
      </CartProvider>
    </AnnouncerProvider>
  );
}
