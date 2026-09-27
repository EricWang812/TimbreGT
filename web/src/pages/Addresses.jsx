import { useEffect, useRef, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { createBuyerAddress, getBuyerAddresses } from "../lib/api.js";
import { signInHref } from "../lib/account.js";

const EMPTY = { recipientName: "", addressLine1: "", addressLine2: "", city: "", stateRegion: "", postalCode: "", country: "United States" };
const FIELDS = [
  ["recipientName", "Recipient name", "name", true],
  ["addressLine1", "Address line 1", "address-line1", true],
  ["addressLine2", "Address line 2 (optional)", "address-line2", false],
  ["city", "City", "address-level2", true],
  ["stateRegion", "State or region", "address-level1", true],
  ["postalCode", "Postal code", "postal-code", true],
  ["country", "Country", "country-name", true],
];

export default function Addresses() {
  const [list, setList] = useState({ status: "loading", addresses: [] });
  const [form, setForm] = useState(EMPTY);
  const [save, setSave] = useState({ status: "idle" });
  const [reload, setReload] = useState(0);
  const firstField = useRef(null);
  useEffect(() => {
    let active = true;
    setList((s) => (s.status === "ready" ? s : { ...s, status: "loading" }));  // keep the form mounted while refreshing
    getBuyerAddresses().then(
      (addresses) => { if (active) setList({ status: "ready", addresses }); },
      (error) => { if (active) setList({ status: error.status === 401 ? "unauthorized" : "error", addresses: [] }); },
    );
    return () => { active = false; };
  }, [reload]);

  async function submit(event) {
    event.preventDefault();
    if (save.status === "saving") return;
    setSave({ status: "saving" });
    try {
      await createBuyerAddress({ ...form, addressLine2: form.addressLine2.trim() || null });
      setForm(EMPTY);
      setSave({ status: "saved" });
      setReload((n) => n + 1);
      firstField.current?.focus();
    } catch (error) {
      setSave({ status: "error", message: error.status === 422 ? "Fill in every required field." : "The address could not be saved. Try again." });
    }
  }

  return <section className="stack">
    <PageHeading>Addresses</PageHeading>
    {list.status === "unauthorized" && <p role="alert">Sign in as a buyer to manage shipping addresses. <a href={signInHref("buyer")}>Sign in</a></p>}
    {list.status === "error" && <p className="message-error" role="alert">Unable to load your addresses. <button type="button" className="btn btn-secondary" onClick={() => setReload((n) => n + 1)}>Try again</button></p>}
    {list.status === "loading" && <p role="status" aria-busy="true">Loading addresses…</p>}
    {list.status === "ready" && <>
      <p className="note">Addresses are private to your buyer account. You only need one if a market ships your order.</p>
      {!list.addresses.length ? <p>No saved addresses yet.</p> : <ul className="address-list">{list.addresses.map((a) => <li key={a.id} className="account-card">
        <address>{a.recipientName}<br />{a.addressLine1}{a.addressLine2 && <><br />{a.addressLine2}</>}<br />{a.city}, {a.stateRegion} {a.postalCode}<br />{a.country}</address>
      </li>)}</ul>}
      <form className="auth-form stack" onSubmit={submit}>
        <h2>Add an address</h2>
        {FIELDS.map(([key, label, autoComplete, required], index) => <label key={key} className="form-field">{label}
          <input ref={index === 0 ? firstField : undefined} name={key} autoComplete={autoComplete} required={required} maxLength={key === "postalCode" ? 32 : 160}
            value={form[key]} onChange={(e) => { setForm({ ...form, [key]: e.target.value }); if (save.status !== "saving") setSave({ status: "idle" }); }} />
        </label>)}
        {save.status === "error" && <p className="message-error" role="alert">{save.message}</p>}
        {save.status === "saved" && <p role="status">Address saved.</p>}
        <button type="submit" className="btn btn-primary" disabled={save.status === "saving"}>{save.status === "saving" ? "Saving…" : "Save address"}</button>
      </form>
    </>}
  </section>;
}
