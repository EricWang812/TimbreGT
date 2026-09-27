import { useEffect, useState } from "react";
import { getBuyerAddresses, getFulfillmentOptions } from "../lib/api.js";

function oneLine(a) {
  return [a.recipientName, a.addressLine1, a.addressLine2, `${a.city}, ${a.stateRegion} ${a.postalCode}`].filter(Boolean).join(", ");
}

// A signed-in buyer chooses how the whole cart arrives. Only methods every
// market in the cart offers are shown; the server checks the same rule again.
export default function DeliveryChoice({ marketIds, marketNames, onChange }) {
  const [state, setState] = useState({ status: "loading" });
  const [method, setMethod] = useState(null);
  const [addressId, setAddressId] = useState("");
  const key = marketIds.join(",");
  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    Promise.all([getBuyerAddresses(), ...marketIds.map(getFulfillmentOptions)]).then(([addresses, ...options]) => {
      if (!active) return;
      const shared = ["SHIP", "PICKUP"].filter((m) => options.every((o) => o.availableMethods.includes(m)));
      setState({ status: "ready", addresses, options, shared });
      const initial = shared.includes("SHIP") && addresses.length ? "SHIP" : shared.includes("PICKUP") ? "PICKUP" : shared[0] ?? null;
      setMethod(initial);
      setAddressId(addresses[0]?.id ?? "");
    }, () => { if (active) setState({ status: "error" }); });
    return () => { active = false; };
  }, [key]);

  const ready = state.status === "ready";
  const valid = ready && (method === "PICKUP" || (method === "SHIP" && addressId));
  useEffect(() => {
    onChange(valid ? { method, ...(method === "SHIP" ? { shippingAddressId: addressId } : {}) } : null);
  }, [valid, method, addressId]);

  if (state.status === "loading") return <p role="status" aria-busy="true">Loading delivery options…</p>;
  if (state.status === "error") return <p className="message-error" role="alert">Delivery options could not load. Reload the page to try again.</p>;
  const { addresses, options, shared } = state;
  if (!shared.length) return <p className="message-error" role="alert">No delivery option covers every market in your cart. Check out one market at a time.</p>;
  return <fieldset className="delivery-choice">
    <legend>How do you want your order?</legend>
    {shared.includes("SHIP") && <div className="delivery-option">
      <label className="radio-option"><input type="radio" name="delivery" checked={method === "SHIP"} onChange={() => setMethod("SHIP")} /> Ship it</label>
      {method === "SHIP" && (addresses.length
        ? <label className="form-field">Ship to<select value={addressId} onChange={(e) => setAddressId(e.target.value)}>{addresses.map((a) => <option key={a.id} value={a.id}>{oneLine(a)}</option>)}</select></label>
        : <p>You have no saved address. <a href="#/addresses">Add a shipping address</a> (your cart is kept).</p>)}
    </div>}
    {shared.includes("PICKUP") && <div className="delivery-option">
      <label className="radio-option"><input type="radio" name="delivery" checked={method === "PICKUP"} onChange={() => setMethod("PICKUP")} /> Pick it up</label>
      {method === "PICKUP" && <ul className="note">{options.map((o) => <li key={o.marketId}>{marketNames[o.marketId] ?? "Market"}: {[o.pickupAddress.addressLine1, o.pickupAddress.addressLine2, o.pickupAddress.city].filter(Boolean).join(", ")}</li>)}</ul>}
    </div>}
  </fieldset>;
}
