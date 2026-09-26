import { useCallback, useEffect, useRef, useState } from "react";
import CartDrawer from "./components/CartDrawer.jsx";
import EnrollPage from "./issuer/EnrollPage.jsx";
import SiteHeader from "./components/SiteHeader.jsx";
import { AnnouncerProvider } from "./lib/announce.jsx";
import { getCatalog } from "./lib/api.js";
import { CartProvider } from "./lib/cart.jsx";
import { useRoute } from "./lib/router.js";
import Baseline from "./pages/Baseline.jsx";
import Checkout from "./pages/Checkout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Receipt from "./pages/Receipt.jsx";
import Shop from "./pages/Shop.jsx";

function useCatalog() {
  const [state, setState] = useState({ status: "loading", products: [], byId: {} });
  const latest = useRef(0);  // only the newest request may update state

  const load = useCallback(() => {
    const request = ++latest.current;
    setState((s) => ({ ...s, status: "loading" }));
    getCatalog().then(
      (products) => request === latest.current && setState({
        status: "ready",
        products,
        byId: Object.fromEntries(products.map((p) => [p.id, p])),
      }),
      (err) => {
        console.error("catalog failed to load", err);
        if (request === latest.current) setState((s) => ({ ...s, status: "error" }));
      },
    );
  }, []);

  useEffect(load, [load]);
  return { ...state, reload: load };
}

function Shell() {
  const route = useRoute();
  const catalog = useCatalog();
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
      <SiteHeader onOpenCart={() => setCartOpen(true)} />
      {/* key: each route mounts fresh, so the .route-enter fade (styles.css) replays on navigation. */}
      <main id="main-content" tabIndex={-1} key={route.name} className="route-enter">
        {route.name === "shop" && <Shop catalog={catalog} />}
        {route.name === "checkout" && <Checkout products={catalog.byId} />}
        {route.name === "baseline" && <Baseline />}
        {route.name === "dashboard" && <Dashboard />}
        {route.name === "receipt" && <Receipt key={route.instructionId} instructionId={route.instructionId} products={catalog.byId} />}
      </main>
      <footer className="site-footer">
        <p className="note">
          Seaside Market is a demo storefront for Timbre. Product photos: Open Food Facts contributors, CC BY-SA 3.0.
        </p>
        <p className="note"><a href="#/bank/enroll">Set up voice approval at your bank (demo)</a></p>
        <p className="note"><a href="#/baseline">Why transcription is the wrong test (demo comparison)</a></p>
        <p className="note"><a href="#/dashboard">Voice changes over time (adaptation demo)</a></p>
      </footer>
      <CartDrawer open={cartOpen} onClose={() => setCartOpen(false)} products={catalog.byId} />
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
