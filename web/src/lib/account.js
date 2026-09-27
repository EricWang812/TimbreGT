// One source of truth for who is signed in. Sign-in, sign-out, and
// registration call notifyAccountChanged() so the header and account pages
// refresh without a page reload.
import { useEffect, useState } from "react";
import { getBuyerSession, getMarketOwnerSession } from "./api.js";

const EVENT = "timbre:account-changed";

export function notifyAccountChanged() {
  window.dispatchEvent(new Event(EVENT));
}

export function useAccountSessions() {
  const [state, setState] = useState({ status: "loading", buyer: null, owner: null });
  useEffect(() => {
    let active = true;
    const load = () => Promise.all([getBuyerSession(), getMarketOwnerSession()]).then(
      ([buyer, owner]) => { if (active) setState({ status: "ready", buyer: buyer.account, owner: owner.account }); },
      () => { if (active) setState({ status: "error", buyer: null, owner: null }); },
    );
    load();
    window.addEventListener(EVENT, load);
    return () => { active = false; window.removeEventListener(EVENT, load); };
  }, []);
  return state;
}

// Where a sign-in should return to. Only in-app paths are allowed, so a crafted
// link can never send someone off the site after they sign in.
export function safeNext(next) {
  return typeof next === "string" && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/sign-in") ? next : null;
}

export function currentPath() {
  return window.location.hash.replace(/^#/, "") || "/";
}

// A sign-in link that brings the person back to the page they were on.
export function signInHref(role, next = currentPath()) {
  const back = safeNext(next);
  return `#/sign-in/${role}${back && back !== "/" ? `?next=${encodeURIComponent(back)}` : ""}`;
}

// A brief visible confirmation (shown by App's Flash) for sign-in and sign-out.
export function flash(text) {
  window.dispatchEvent(new CustomEvent("timbre:flash", { detail: text }));
}
