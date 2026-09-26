// Minimal hash router: three routes do not justify a routing dependency.
// Hash URLs keep deep links and the browser back button working.
import { useEffect, useState } from "react";

let hasNavigated = false;

function parse(hash) {
  const path = hash.replace(/^#/, "") || "/";
  const receipt = path.match(/^\/receipt\/([0-9a-f-]{36})$/i);
  if (receipt) return { name: "receipt", instructionId: receipt[1] };
  // The bank's own app (issuer surface), mounted at its own route.
  const enroll = path.match(/^\/bank\/enroll(?:\/([A-Za-z0-9_-]{1,64}))?$/);
  if (enroll) return { name: "bank-enroll", userId: enroll[1] ?? null };
  if (path === "/checkout") return { name: "checkout" };
  if (path === "/baseline") return { name: "baseline" };
  if (path === "/dashboard") return { name: "dashboard" };
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
