import { useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { flash, notifyAccountChanged, safeNext, useAccountSessions } from "../lib/account.js";
import { loginBuyer, loginMarketOwner, registerBuyer, registerMarketOwner } from "../lib/api.js";
import { navigate } from "../lib/router.js";

const ROLES = {
  buyer: { label: "Buyer", noun: "buyer", home: "/buyer-dashboard", signIn: loginBuyer, create: registerBuyer },
  owner: { label: "Market owner", noun: "market owner", home: "/market-dashboard", signIn: loginMarketOwner, create: registerMarketOwner },
};

function authError(error, role, mode) {
  if (error.status === 401) return `No ${ROLES[role].noun} account matches that email and password. Check the account type and try again.`;
  if (error.status === 409) return "An account with this email already exists. Choose Sign in instead.";
  if (error.status === 422) return "Enter a valid email address and a password of 12 to 128 characters.";
  return `${mode === "create" ? "Account creation" : "Sign-in"} is unavailable right now. Try again in a moment.`;
}

// Shopping and checkout never require an account; this page is for order
// history (buyers) and market management (owners). Purchase approval stays
// with the bank's voice or passkey check.
export default function SignIn({ role: initialRole = "buyer", next = null }) {
  const sessions = useAccountSessions();
  const returnTo = safeNext(next);
  const [role, setRole] = useState(ROLES[initialRole] ? initialRole : "buyer");
  const [mode, setMode] = useState("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [state, setState] = useState({ status: "idle" });
  const creating = mode === "create";

  async function submit(event) {
    event.preventDefault();
    if (state.status === "submitting") return;
    setState({ status: "submitting" });
    try {
      const account = await ROLES[role][creating ? "create" : "signIn"](email, password);
      notifyAccountChanged();
      // Back to the page that asked for sign-in (checkout, orders...), else the role's home.
      navigate(returnTo ?? ROLES[role].home);
      flash(creating ? `Account created. Signed in as ${account.email}.` : `Signed in as ${account.email}.`);
    } catch (error) {
      setState({ status: "error", message: authError(error, role, mode) });
    }
  }

  function switchMode(next) {
    setMode(next);
    setState({ status: "idle" });
  }

  const current = role === "owner" ? sessions.owner : sessions.buyer;
  const failed = state.status === "error";
  return <section className="stack auth-page">
    <PageHeading>{creating ? "Create an account" : "Sign in"}</PageHeading>
    <p className="note">You can shop and check out without an account. Sign in to see your orders or manage a market.</p>
    {current && <p className="auth-signed-in" role="status">You are already signed in as <strong className="break-anywhere">{current.email}</strong>. <a href={`#${returnTo ?? ROLES[role].home}`}>{returnTo ? "Continue" : `Go to your ${role === "owner" ? "market dashboard" : "dashboard"}`}</a></p>}
    <div className="segmented" role="group" aria-label="Choose an action">
      <button type="button" className="chip" aria-pressed={!creating} onClick={() => switchMode("sign-in")}>Sign in</button>
      <button type="button" className="chip" aria-pressed={creating} onClick={() => switchMode("create")}>Create account</button>
    </div>
    <form className="auth-form stack" onSubmit={submit}>
      <fieldset className="role-choice">
        <legend>Account type</legend>
        {Object.entries(ROLES).map(([id, { label }]) => <label key={id} className="radio-option">
          <input type="radio" name="role" value={id} checked={role === id} onChange={() => { setRole(id); setState({ status: "idle" }); }} />
          {label}
        </label>)}
      </fieldset>
      <label className="form-field">Email
        <input type="email" name="email" autoComplete="email" required maxLength={254} value={email} onChange={(e) => setEmail(e.target.value)}
          aria-invalid={failed || undefined} aria-describedby={failed ? "auth-error" : undefined} />
      </label>
      <label className="form-field">Password
        <input type={showPassword ? "text" : "password"} name="password" required minLength={12} maxLength={128}
          autoComplete={creating ? "new-password" : "current-password"} aria-describedby={failed ? "password-hint auth-error" : "password-hint"} aria-invalid={failed || undefined}
          value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      <p id="password-hint" className="note">At least 12 characters. A short phrase works well.</p>
      <label className="checkbox-option"><input type="checkbox" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)} /> Show password</label>
      {failed && <p id="auth-error" className="message-error" role="alert">{state.message}</p>}
      <button type="submit" className="btn btn-primary btn-large" disabled={state.status === "submitting"}>
        {state.status === "submitting" ? (creating ? "Creating account…" : "Signing in…") : creating ? `Create ${ROLES[role].noun} account` : `Sign in as ${ROLES[role].noun}`}
      </button>
    </form>
    <p className="note">No password reset is available in this demo. Market owner and buyer accounts are separate, and each email can hold one account.</p>
  </section>;
}
