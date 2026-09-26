// Minimal hash router: three routes do not justify a routing dependency.
// Hash URLs keep deep links and the browser back button working.
import { useEffect, useState } from "react";

let hasNavigated = false;

function parse(hash) {
  const path = hash.replace(/^#/, "") || "/";
  const receipt = path.match(/^\/receipt\/([0-9a-f-]{36})$/i);
  if (receipt) return { name: "receipt", instructionId: receipt[1] };
  const market = path.match(/^\/markets\/([0-9a-f-]{36})$/i);
  if (market) return { name: "market", marketId: market[1] };
  // The bank's own app (issuer surface), mounted at its own route.
  const enroll = path.match(/^\/bank\/enroll(?:\/([A-Za-z0-9_-]{1,64}))?$/);
  if (enroll) return { name: "bank-enroll", userId: enroll[1] ?? null };
  if (path === "/checkout") return { name: "checkout" };
  if (path === "/baseline") return { name: "baseline" };
  if (path === "/dashboard") return { name: "dashboard" };
  if (path === "/buyer-dashboard") return { name: "buyer-dashboard" };
  const analytics = path.match(/^\/market-analytics(?:\/([^/]+))?$/);
  if (analytics) return { name: "market-analytics", marketId: analytics[1] };
  const marketOrders = path.match(/^\/market-orders(?:\/([^/]+))?$/);
  if (marketOrders) return { name: "market-orders", marketId: marketOrders[1] };
  const managed = path.match(/^\/market-dashboard\/([^/]+)(?:\/orders\/([^/]+))?$/);
  if (managed) return { name: "market-dashboard", marketId: managed[1], orderId: managed[2] };
  if (path === "/market-dashboard") return { name: "market-dashboard" };
  if (path === "/buyer-orders") return { name: "buyer-orders" };
  const buyerOrder = path.match(/^\/buyer-orders\/([0-9a-f-]{36})$/i);
  if (buyerOrder) return { name: "buyer-order", orderId: buyerOrder[1] };
  return { name: "shop" };
}

export function useRoute() {
  const [route, setRoute] = useState(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      hasNavigated = true;
      setRoute(parse(window.location.hash));
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(path) {
  window.location.hash = path;
}

// Pages move focus to their heading after a navigation (not on first load),
// so screen reader and keyboard users land at the new content.
export function shouldFocusHeading() {
  return hasNavigated;
}
