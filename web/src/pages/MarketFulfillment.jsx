import { useEffect, useState } from "react";
import { getPickupSettings, getShippingSettings, updatePickupSettings, updateShippingSettings } from "../lib/api.js";

// A signed-in buyer can only check out from a market that offers pickup or
// shipping, so this is where a new seller turns those on.
const METHODS = [["USPS", "USPS"], ["UPS", "UPS"], ["FEDEX", "FedEx"], ["LOCAL_DRIVER", "Local driver"]];
const BLANK = { addressLine1: "", addressLine2: "", city: "", stateRegion: "", postalCode: "", country: "United States" };

export default function MarketFulfillment({ market }) {
  const [state, setState] = useState({ status: "loading" });
  const [pickup, setPickup] = useState({ enabled: false, address: BLANK });
  const [shipping, setShipping] = useState({ enabled: false, methods: [] });
  const [saving, setSaving] = useState(null);
  const [message, setMessage] = useState(null);
  useEffect(() => {
    let active = true;
    Promise.all([getPickupSettings(market.id), getShippingSettings(market.id)]).then(([p, s]) => {
      if (!active) return;
      setPickup({ enabled: p.pickupEnabled, address: { ...BLANK, ...(p.pickupAddress ?? {}), addressLine2: p.pickupAddress?.addressLine2 ?? "" } });
      setShipping({ enabled: s.shippingEnabled, methods: s.supportedShippingMethods });
      setState({ status: "ready" });
    }, () => { if (active) setState({ status: "error" }); });
    return () => { active = false; };
  }, [market.id]);

  async function savePickup(event) {
    event.preventDefault();
    setSaving("pickup"); setMessage(null);
    try {
      const address = { ...pickup.address, addressLine2: pickup.address.addressLine2.trim() || null };
      await updatePickupSettings(market.id, pickup.enabled ? { pickupAddress: address, pickupEnabled: true } : { pickupEnabled: false });
      setMessage({ text: pickup.enabled ? "Pickup is on. Buyers can choose it at checkout." : "Pickup is off." });
    } catch (error) {
      setMessage({ error: true, text: error.status === 422 ? "Fill in every required pickup address field." : "Pickup settings could not be saved." });
    } finally { setSaving(null); }
  }
  async function saveShipping(event) {
    event.preventDefault();
    if (shipping.enabled && !shipping.methods.length) { setMessage({ error: true, text: "Choose at least one shipping method, or turn shipping off." }); return; }
    setSaving("shipping"); setMessage(null);
    try {
      // Methods before enabling, disabling before clearing: the server never allows shipping on with no method.
      if (shipping.enabled) {
        await updateShippingSettings(market.id, { supportedShippingMethods: shipping.methods });
        await updateShippingSettings(market.id, { shippingEnabled: true });
      } else {
        await updateShippingSettings(market.id, { shippingEnabled: false });
        await updateShippingSettings(market.id, { supportedShippingMethods: shipping.methods });
      }
      setMessage({ text: shipping.enabled ? "Shipping is on. Buyers can choose it at checkout." : "Shipping is off." });
    } catch {
      setMessage({ error: true, text: "Shipping settings could not be saved." });
    } finally { setSaving(null); }
  }

  if (state.status === "loading") return <p role="status" aria-busy="true">Loading delivery settings…</p>;
  if (state.status === "error") return <p className="message-error" role="alert">Unable to load delivery settings. Refresh to try again.</p>;
  const setAddress = (key) => (e) => setPickup({ ...pickup, address: { ...pickup.address, [key]: e.target.value } });
  return <section className="stack" aria-labelledby="delivery-title">
    <div>
      <h3 id="delivery-title">Delivery</h3>
      <p className="note">Signed-in buyers choose pickup or shipping at checkout. Turn on at least one so they can buy from {market.name}.</p>
    </div>
    <p className={message?.error ? "message-error" : "purchase-message"} role={message?.error ? "alert" : "status"}>{message?.text}</p>
    <div className="seller-settings">
      <form className="seller-panel stack" onSubmit={savePickup}>
        <h4>Pickup</h4>
        <label className="checkbox-option"><input type="checkbox" checked={pickup.enabled} onChange={(e) => setPickup({ ...pickup, enabled: e.target.checked })} /> Offer pickup</label>
        {pickup.enabled && <div className="product-form-grid">
          <label className="form-field product-form-name">Street address<input required value={pickup.address.addressLine1} onChange={setAddress("addressLine1")} autoComplete="address-line1" /></label>
          <label className="form-field product-form-name"><span className="field-label">Pickup notes <span className="note">(optional)</span></span><input value={pickup.address.addressLine2} onChange={setAddress("addressLine2")} placeholder="Stall 4, next to the pier" /></label>
          <label className="form-field">City<input required value={pickup.address.city} onChange={setAddress("city")} autoComplete="address-level2" /></label>
          <label className="form-field">State or region<input required value={pickup.address.stateRegion} onChange={setAddress("stateRegion")} autoComplete="address-level1" /></label>
          <label className="form-field">Postal code<input required value={pickup.address.postalCode} onChange={setAddress("postalCode")} autoComplete="postal-code" /></label>
          <label className="form-field">Country<input required value={pickup.address.country} onChange={setAddress("country")} autoComplete="country-name" /></label>
        </div>}
        <p><button type="submit" className="btn btn-primary" disabled={saving === "pickup"}>{saving === "pickup" ? "Saving…" : "Save pickup"}</button></p>
      </form>
      <form className="seller-panel stack" onSubmit={saveShipping}>
        <h4>Shipping</h4>
        <label className="checkbox-option"><input type="checkbox" checked={shipping.enabled} onChange={(e) => setShipping({ ...shipping, enabled: e.target.checked })} /> Offer shipping</label>
        <fieldset className="role-choice" disabled={!shipping.enabled}>
          <legend>Carriers you ship with</legend>
          {METHODS.map(([id, label]) => <label key={id} className="checkbox-option"><input type="checkbox" checked={shipping.methods.includes(id)}
            onChange={(e) => setShipping({ ...shipping, methods: e.target.checked ? [...shipping.methods, id] : shipping.methods.filter((m) => m !== id) })} /> {label}</label>)}
        </fieldset>
        <p><button type="submit" className="btn btn-primary" disabled={saving === "shipping"}>{saving === "shipping" ? "Saving…" : "Save shipping"}</button></p>
      </form>
    </div>
  </section>;
}
