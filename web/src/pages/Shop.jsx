import { useEffect, useState } from "react";
import VoiceShopping from "../components/VoiceShopping.jsx";
import AgenticVoiceShopping from "../components/AgenticVoiceShopping.jsx";
import PageHeading from "../components/PageHeading.jsx";
import ProductCard, { SkeletonCard } from "../components/ProductCard.jsx";
import { LockIcon, TruckIcon } from "../components/Icons.jsx";
import { scrollAndFocus } from "../components/jump.js";

// Display sections, in order. Seafood leads: it is a seaside market. Small
// catalog categories are merged so no section is a lone card in a wide row.
const SECTIONS = [
  ["sea", "From the sea", ["seafood"]],
  ["fresh", "Fresh and dairy", ["produce", "bakery", "dairy"]],
  ["drinks", "Drinks", ["drinks"]],
  ["pantry", "Pantry and snacks", ["pantry", "snacks"]],
];
const SKELETON_CARDS = 8;
// Grid entrance: each card starts a little after the one before, capped so the
// whole grid has finished within about half a second.
const STAGGER_MS = 25;
const STAGGER_CAP_MS = 220;
const ENTRANCE_MS = 700;   // after this the entrance class is removed for good

// The grid entrance plays once per page load, not on every return to the shop.
let gridHasEntered = false;

function useGridEntrance(ready) {
  const [entering, setEntering] = useState(!gridHasEntered);
  useEffect(() => {
    if (!ready || !entering) return undefined;
    gridHasEntered = true;
    // Time-based, never animationend: that event does not fire when motion is off.
    const id = setTimeout(() => setEntering(false), ENTRANCE_MS);
    return () => clearTimeout(id);
  }, [ready, entering]);
  return entering;
}

function itemsText(n) {
  return n === 1 ? "1 item" : `${n} items`;
}

export default function Shop({ catalog, onOpenCart }) {
  const groups = SECTIONS
    .map(([key, label, categories]) => [key, label, catalog.products.filter((p) => categories.includes(p.category))])
    .filter(([, , items]) => items.length > 0);
  const known = new Set(SECTIONS.flatMap(([, , categories]) => categories));
  const other = catalog.products.filter((p) => !known.has(p.category));
  if (other.length) groups.push(["other", "More", other]);

  const loading = catalog.status === "loading";
  const showVoice = !loading && catalog.products.length > 0;
  const entering = useGridEntrance(catalog.status === "ready");

  // A plain href="#pantry" would be read as a route by the hash router.
  function jumpTo(event, key) {
    event.preventDefault();
    scrollAndFocus(document.getElementById(`category-${key}`));
  }

  let order = 0;   // running card index across sections, for the stagger
  return (
    <>
      <div className={`market-band${showVoice || loading ? "" : " is-single"}`}>
        <div className="band-intro">
          <PageHeading>Shop the market</PageHeading>
          <p className="band-lead">Fresh from the coast. Add items by voice, with a tap, or with the keyboard.</p>
          <ul className="fact-pills">
            <li><TruckIcon size={20} /> Free delivery on orders of $35 or more</li>
            <li><LockIcon size={20} /> Approve payment with your bank</li>
          </ul>
        </div>
        {showVoice && <VoiceShopping products={catalog.products} />}
        {loading && <div className="voice-shopping voice-placeholder" aria-hidden="true" />}
      </div>

      {showVoice && <AgenticVoiceShopping onOpenCart={onOpenCart} />}

      {loading && (
        <div className="stack">
          <p className="note" aria-busy="true">Loading products…</p>
          <ul className="product-grid is-skeleton" aria-hidden="true">
            {Array.from({ length: SKELETON_CARDS }, (_, i) => <li key={i}><SkeletonCard /></li>)}
          </ul>
        </div>
      )}
      {catalog.status === "error" && (
        <div className="stack">
          <p className="message-error" role="alert">The product list could not load.</p>
          <p><button type="button" className="btn btn-secondary" onClick={catalog.reload}>Try again</button></p>
        </div>
      )}

      {!loading && groups.length > 0 && (
        <nav className="aisle-nav" aria-label="Shop by aisle">
          <ul className="aisle-chips">
            {groups.map(([key, label, items]) => (
              <li key={key}>
                <a className="chip" href={`#category-${key}`} onClick={(e) => jumpTo(e, key)}>
                  {label}
                  <span className="chip-count" aria-hidden="true">{items.length}</span>
                  <span className="visually-hidden">, {itemsText(items.length)}</span>
                </a>
              </li>
            ))}
          </ul>
        </nav>
      )}

      {!loading && groups.map(([key, label, items]) => (
        <section key={key} className="category" aria-labelledby={`category-${key}`}>
          <div className="section-head">
            <h2 id={`category-${key}`} tabIndex={-1}>{label}</h2>
            <p className="section-count">{itemsText(items.length)}</p>
          </div>
          <ul className={`product-grid${items.length <= 2 ? " is-feature" : ""}${entering ? " is-entering" : ""}`}>
            {items.map((p) => {
              const delay = Math.min(order++ * STAGGER_MS, STAGGER_CAP_MS);
              return <li key={p.id} style={{ "--enter-delay": `${delay}ms` }}><ProductCard product={p} /></li>;
            })}
          </ul>
        </section>
      ))}
    </>
  );
}
