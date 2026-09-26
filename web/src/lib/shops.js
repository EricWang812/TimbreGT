// The boardwalk: themed shops that share one catalog, one cart, and one
// checkout. Names and taglines come from the merchant (GET /store, from
// api/catalog.py MARKETS); this file only decides how each shop's shelves
// are laid out. Colors live in styles.css under [data-market].
import { useEffect, useState } from "react";
import { getStoreInfo } from "./api.js";

// Aisles per shop, in walking order: [key, heading, catalog categories].
export const SHOP_SECTIONS = {
  // Seafood leads: it is a seaside market. The rest follow a store walk:
  // fresh first, then chilled, frozen, and shelf aisles.
  grocer: [
    ["sea", "From the sea", ["seafood"]],
    ["produce", "Fruit and vegetables", ["produce"]],
    ["bakery", "Bakery", ["bakery"]],
    ["dairy", "Dairy and eggs", ["dairy"]],
    ["meat", "Meat and deli", ["meat"]],
    ["frozen", "Frozen", ["frozen"]],
    ["breakfast", "Breakfast", ["breakfast"]],
    ["pantry", "Pantry", ["pantry"]],
    ["snacks", "Snacks", ["snacks"]],
    ["drinks", "Drinks", ["drinks"]],
  ],
  tech: [
    ["audio", "Headphones and speakers", ["audio"]],
    ["power", "Chargers and batteries", ["power"]],
  ],
  sun: [
    ["sun", "Sun protection", ["sun"]],
    ["care", "Lip and skin care", ["care"]],
  ],
  pets: [
    ["dog", "For dogs", ["dog"]],
    ["cat", "For cats", ["cat"]],
  ],
};
export const DEFAULT_SHOP = "grocer";   // products seeded without a shop

// One request per page load, shared by every component that needs store facts.
let pending = null;
function loadStoreInfo() {
  pending ??= getStoreInfo().catch((err) => {
    pending = null;   // let a later mount try again
    throw err;
  });
  return pending;
}

// {freeShippingMinCents, markets}. If the store facts cannot load, markets is
// empty and callers fall back to one unlabeled shop rather than guessing names.
export function useStoreInfo() {
  const [info, setInfo] = useState({ freeShippingMinCents: null, markets: [] });
  useEffect(() => {
    let cancelled = false;
    loadStoreInfo().then(
      (data) => {
        if (cancelled) return;
        setInfo({
          freeShippingMinCents: Number.isInteger(data.free_shipping_min_cents) ? data.free_shipping_min_cents : null,
          markets: Array.isArray(data.markets) ? data.markets : [],
        });
      },
      (err) => console.error("store info unavailable; shop names and delivery pill hidden", err),
    );
    return () => { cancelled = true; };
  }, []);
  return info;
}

export function shopOf(product) {
  return product?.market ?? DEFAULT_SHOP;
}

// The shop's display name for a product, or null when names are unknown or
// there is only one shop (then naming it on every line adds nothing).
export function shopNameFor(product, markets) {
  if (!product || markets.length < 2) return null;
  return markets.find((m) => m.id === shopOf(product))?.name ?? null;
}
