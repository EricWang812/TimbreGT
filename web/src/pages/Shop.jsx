import { useEffect, useState } from "react";
import VoiceShopping from "../components/VoiceShopping.jsx";
import AgenticVoiceShopping from "../components/AgenticVoiceShopping.jsx";
import PageHeading from "../components/PageHeading.jsx";
import ProductCard, { SkeletonCard } from "../components/ProductCard.jsx";
import { FishIcon, HeadphonesIcon, LockIcon, PawIcon, SunIcon, TruckIcon, WavesIcon } from "../components/Icons.jsx";
import { scrollAndFocus } from "../components/jump.js";
import { useAnnounce } from "../lib/announce.jsx";
import { formatCents } from "../lib/money.js";
import { SHOP_SECTIONS, shopOf, useStoreInfo } from "../lib/shops.js";

const SHOP_ICONS = { grocer: FishIcon, tech: HeadphonesIcon, sun: SunIcon, pets: PawIcon };
const ALL = "all";
const SAVED_SHOP_KEY = "timbre.shop";   // per-viewer convenience only
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

function readSavedShop() {
  try { return localStorage.getItem(SAVED_SHOP_KEY) ?? ALL; } catch { return ALL; }
}

function saveShop(id) {
  try { localStorage.setItem(SAVED_SHOP_KEY, id); } catch { /* private mode: not remembered */ }
}

function itemsText(n) {
  return n === 1 ? "1 item" : `${n} items`;
}

// Each shop with its aisles. Without shop names from the store (it could not
// load), everything shows as one unlabeled shop, laid out by every known aisle.
function buildShops(products, markets) {
  const list = markets.length ? markets : [{ id: null, name: null, tagline: null }];
  return list.map((shop) => {
    const stock = shop.id ? products.filter((p) => shopOf(p) === shop.id) : products;
    const sections = SHOP_SECTIONS[shop.id] ?? Object.values(SHOP_SECTIONS).flat();
    const groups = sections
      .map(([key, label, categories]) => [key, label, stock.filter((p) => categories.includes(p.category))])
      .filter(([, , items]) => items.length > 0);
    const known = new Set(sections.flatMap(([, , categories]) => categories));
    const other = stock.filter((p) => !known.has(p.category));
    if (other.length) groups.push(["other", "More", other]);
    return { ...shop, count: stock.length, groups };
  }).filter((shop) => shop.count > 0);
}

function Awning() {
  return <span className="shop-awning" aria-hidden="true" />;
}

function ShopSign({ id, name, tagline, count, pressed, onChoose }) {
  const Icon = SHOP_ICONS[id] ?? WavesIcon;
  return (
    <button type="button" className="shop-sign" data-market={id} aria-pressed={pressed} onClick={onChoose}>
      <Awning />
      <span className="shop-sign-body">
        <span className="shop-sign-icon"><Icon size={26} /></span>
        <span className="shop-sign-name">{name}</span>
        <span className="shop-sign-tagline">{tagline}</span>
        <span className="shop-sign-foot">
          <span className="shop-sign-count">{itemsText(count)}</span>
          {pressed && <span className="shop-sign-showing">Showing</span>}
        </span>
      </span>
    </button>
  );
}

export default function Shop({ catalog, onOpenCart }) {
  const { freeShippingMinCents, markets } = useStoreInfo();
  const announce = useAnnounce();
  const shops = buildShops(catalog.products, markets);
  const [chosen, setChosen] = useState(readSavedShop);
  const selected = shops.some((s) => s.id === chosen) ? chosen : ALL;
  const visible = selected === ALL ? shops : shops.filter((s) => s.id === selected);
  const boardwalk = shops.length > 1;

  const loading = catalog.status === "loading";
  const showVoice = !loading && catalog.products.length > 0;
  const entering = useGridEntrance(catalog.status === "ready");

  function choose(id) {
    setChosen(id);
    saveShop(id);
    const shop = shops.find((s) => s.id === id);
    announce(shop ? `Showing ${shop.name}, ${itemsText(shop.count)}.` : `Showing every shop, ${itemsText(catalog.products.length)}.`);
  }

  // Buttons, not links: a chip moves focus on this page and never navigates.
  function jumpTo(id) {
    scrollAndFocus(document.getElementById(id));
  }

  // Aisle chips for the shop on show; with every shop showing, the signs and
  // banners do that job and sixteen chips would only be noise.
  const chips = visible.length === 1 ? visible[0].groups.map(([key, label, items]) => [
    `category-${visible[0].id ?? "all"}-${key}`, label, items.length]) : [];

  let order = 0;   // running card index across sections, for the stagger
  return (
    <>
      <div className={`market-band${showVoice || loading ? "" : " is-single"}`}>
        <div className="band-intro">
          <PageHeading>{boardwalk ? "Shop the boardwalk" : "Shop the market"}</PageHeading>
          <p className="band-lead">
            {boardwalk
              ? `${shops.length} shops by the sea, one cart. Add items by voice, with a tap, or with the keyboard.`
              : "Fresh from the coast. Add items by voice, with a tap, or with the keyboard."}
          </p>
          <ul className="fact-pills">
            {freeShippingMinCents !== null && (
              <li><TruckIcon size={20} /> Free delivery on orders of {formatCents(freeShippingMinCents).replace(/\.00$/, "")} or more</li>
            )}
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

      {!loading && boardwalk && (
        <nav className="boardwalk" aria-labelledby="boardwalk-title">
          <div className="section-head">
            <h2 id="boardwalk-title">Shops on the boardwalk</h2>
            <p className="section-count">One cart and one checkout for all of them</p>
          </div>
          <ul className="shop-signs">
            <li>
              <ShopSign id={ALL} name="All shops" tagline="Stroll the whole boardwalk."
                count={catalog.products.length} pressed={selected === ALL} onChoose={() => choose(ALL)} />
            </li>
            {shops.map((shop) => (
              <li key={shop.id}>
                <ShopSign id={shop.id} name={shop.name} tagline={shop.tagline} count={shop.count}
                  pressed={selected === shop.id} onChoose={() => choose(shop.id)} />
              </li>
            ))}
          </ul>
        </nav>
      )}

      {!loading && chips.length > 1 && (
        <nav className="aisle-nav" aria-label="Shop by aisle">
          <ul className="aisle-chips">
            {chips.map(([id, label, count]) => (
              <li key={id}>
                <button type="button" className="chip" onClick={() => jumpTo(id)}>
                  {label}
                  <span className="chip-count" aria-hidden="true">{count}</span>
                  <span className="visually-hidden">, {itemsText(count)}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
      )}

      {!loading && visible.map((shop) => {
        const Icon = SHOP_ICONS[shop.id] ?? WavesIcon;
        // Shop banners are h2 and aisles h3; with no shop names, aisles are h2.
        const AisleHeading = shop.name ? "h3" : "h2";
        return (
          <section key={shop.id ?? ALL} className="shop" data-market={shop.id ?? undefined}
            aria-labelledby={shop.name ? `shop-${shop.id}` : undefined}>
            {shop.name && (
              <header className="shop-banner">
                <Awning />
                <div className="shop-banner-body">
                  <span className="shop-banner-icon"><Icon size={32} /></span>
                  <div>
                    <h2 id={`shop-${shop.id}`} tabIndex={-1}>{shop.name}</h2>
                    <p className="shop-banner-tagline">{shop.tagline}</p>
                  </div>
                  <p className="shop-banner-count">{itemsText(shop.count)}</p>
                </div>
              </header>
            )}
            {shop.groups.map(([key, label, items]) => {
              const headingId = `category-${shop.id ?? "all"}-${key}`;
              return (
                <section key={key} className="category" aria-labelledby={headingId}>
                  <div className="section-head">
                    <AisleHeading id={headingId} tabIndex={-1}>{label}</AisleHeading>
                    <p className="section-count">{itemsText(items.length)}</p>
                  </div>
                  <ul className={`product-grid${items.length <= 2 ? " is-feature" : ""}${entering ? " is-entering" : ""}`}>
                    {items.map((p) => {
                      const delay = Math.min(order++ * STAGGER_MS, STAGGER_CAP_MS);
                      return <li key={p.id} style={{ "--enter-delay": `${delay}ms` }}><ProductCard product={p} /></li>;
                    })}
                  </ul>
                </section>
              );
            })}
          </section>
        );
      })}
    </>
  );
}
