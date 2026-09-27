import { useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { flash, notifyAccountChanged, signInHref, useAccountSessions } from "../lib/account.js";
import { navigate } from "../lib/router.js";
import { logoutBuyer, logoutMarketOwner } from "../lib/api.js";

function AccountCard({ title, account, role, otherSignedIn, links, onSignOut }) {
  const [state, setState] = useState("idle");
  async function signOut() {
    setState("busy");
    try {
      await onSignOut();
      notifyAccountChanged();
      setState("idle");
      // With no session left there is nothing to manage here, so go to the store.
      if (!otherSignedIn) navigate("/");
      flash(otherSignedIn ? `Signed out of your ${title.toLowerCase()}.` : "You are signed out.");
    } catch { setState("error"); }
  }
  return <section className="account-card stack">
    <h2>{title}</h2>
    {account ? <>
      <p>Signed in as <strong className="break-anywhere">{account.email}</strong></p>
      <nav className="management-actions" aria-label={`${title} links`}>{links.map(([href, label]) => <a key={href} href={href}>{label}</a>)}</nav>
      <p><button type="button" className="btn btn-secondary" disabled={state === "busy"} onClick={signOut}>Sign out of {title.toLowerCase()}</button></p>
      {state === "error" && <p className="message-error" role="alert">Sign-out failed. Try again.</p>}
    </> : <p>Not signed in. <a href={signInHref(role, "/account")}>Sign in or create an account</a></p>}
  </section>;
}

export default function Account() {
  const sessions = useAccountSessions();
  return <section className="stack">
    <PageHeading>Account settings</PageHeading>
    {sessions.status === "loading" && <p role="status">Checking your sessions…</p>}
    {sessions.status === "error" && <p className="message-error" role="alert">Unable to reach the store to check your sessions. Refresh to try again.</p>}
    {sessions.status === "ready" && <div className="account-grid">
      <AccountCard title="Buyer account" account={sessions.buyer} role="buyer" otherSignedIn={Boolean(sessions.owner)} onSignOut={logoutBuyer}
        links={[["#/buyer-dashboard", "Buyer Dashboard"], ["#/buyer-orders", "Orders"], ["#/addresses", "Addresses"]]} />
      <AccountCard title="Market owner account" account={sessions.owner} role="owner" otherSignedIn={Boolean(sessions.buyer)} onSignOut={logoutMarketOwner}
        links={[["#/market-dashboard", "Market Dashboard"]]} />
    </div>}
    <p className="note">Your card and voice approval live with your bank, not in these accounts. Password changes and resets are not available in this demo.</p>
  </section>;
}
