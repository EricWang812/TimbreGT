import { useLayoutEffect, useRef, useState } from "react";
import { CheckIcon, MinusIcon, PlusIcon, TrashIcon } from "./Icons.jsx";
import { itemCountText, MAX_QUANTITY, useCart } from "../lib/cart.jsx";
import { useAnnounce } from "../lib/announce.jsx";
import { formatCents } from "../lib/money.js";

// Unit price from the catalog's size text, only when it parses cleanly
// ("5 oz", "52 fl oz", "2 lb", "750 ml"). Anything else shows no unit price.
const SIZE = /^(\d+(?:\.\d+)?)\s*(fl oz|oz|lb|ml)$/i;
const UNITS = {
  "oz": [1, "oz", "ounce"],
  "fl oz": [1, "fl oz", "fluid ounce"],
  "lb": [1, "lb", "pound"],
  "ml": [100, "100 ml", "100 milliliters"],
};

export function unitPrice(size, cents) {
  const match = SIZE.exec((size ?? "").trim());
  if (!match) return null;
  const amount = Number(match[1]);
  if (!(amount > 0)) return null;
  const [per, short, long] = UNITS[match[2].toLowerCase()];
  const each = (cents / amount) * per;
  const price = each >= 100 ? formatCents(Math.round(each)) : `${each.toFixed(1)}¢`;
  return { shown: `${price}/${short}`, spoken: `${price} per ${long}` };
}

// A10: the photo fades in over the skeleton tint once it has loaded. The
// effect also catches images the browser already had cached, whose load event
// can fire before React attaches onLoad.
function ProductPhoto({ src }) {
  const ref = useRef(null);
  const [loaded, setLoaded] = useState(false);
  useLayoutEffect(() => {
    if (ref.current?.complete) setLoaded(true);
  }, []);
  return (
    <div className="product-well" data-loaded={loaded ? "" : undefined}>
      {/* alt="" because the brand and name are the adjacent text; describing
          the photo again would make screen readers repeat every product. */}
      <img ref={ref} className="product-photo" src={src} alt="" width="240" height="240"
        loading="lazy" decoding="async" onLoad={() => setLoaded(true)} onError={() => setLoaded(true)} />
    </div>
  );
}

export default function ProductCard({ product }) {
  const cart = useCart();
  const announce = useAnnounce();
  const inCart = cart.quantityOf(product.id);
  const atLimit = inCart >= MAX_QUANTITY;
  const label = `${product.brand} ${product.name}`;
  const unit = unitPrice(product.size, product.price_cents);

  // Add swaps for the stepper (and back). The focused button disappears, so
  // focus follows to its replacement, but only when this card caused it.
  const addRef = useRef(null);
  const plusRef = useRef(null);
  const pendingFocus = useRef(null);
  useLayoutEffect(() => {
    const target = pendingFocus.current;
    pendingFocus.current = null;
    if (target === "plus") plusRef.current?.focus();
    if (target === "add") addRef.current?.focus();
  }, [inCart]);

  function add() {
    if (atLimit) {
      // aria-disabled keeps the button focusable, so say why nothing happened.
      announce(`Maximum quantity reached for ${label}: ${MAX_QUANTITY}.`);
      return;
    }
    if (inCart === 0) pendingFocus.current = "plus";
    cart.add(product.id);
    announce(inCart === 0
      ? `Added ${label}. ${itemCountText(cart.count + 1)}.`
      : `${label}: quantity ${inCart + 1}. ${itemCountText(cart.count + 1)}.`);
  }

  function removeOne() {
    const next = inCart - 1;
    if (next <= 0) pendingFocus.current = "add";
    cart.adjust(product.id, -1);
    announce(next <= 0
      ? `Removed ${label}. ${itemCountText(cart.count - 1)}.`
      : `${label}: quantity ${next}. ${itemCountText(cart.count - 1)}.`);
  }

  return (
    <article className="product-card" aria-labelledby={`product-${product.id}`}>
      <ProductPhoto src={product.image_url} />
      {inCart > 0 && <p className="in-cart-badge"><CheckIcon size={16} /> In cart: {inCart}</p>}
      <div className="product-body">
        <p className="product-brand">{product.brand}</p>
        <h3 className="product-name" id={`product-${product.id}`}>{product.name}</h3>
        <p className="product-size">
          {product.size}
          {unit && <>
            <span aria-hidden="true"> · {unit.shown}</span>
            <span className="visually-hidden">, {unit.spoken}</span>
          </>}
        </p>
        <p className="price product-price">{formatCents(product.price_cents)}</p>
        <div className="product-action">
          {inCart === 0 ? (
            <button ref={addRef} type="button" className="btn btn-primary btn-add" onClick={add}
              aria-label={`Add to cart: ${label}`}>
              <PlusIcon size={20} /> Add
            </button>
          ) : (
            <div className="qty-stepper" role="group" aria-label={`Quantity: ${label}`}>
              <button type="button" className="qty-btn" onClick={removeOne} aria-label={`Remove one ${label}`}>
                {inCart === 1 ? <TrashIcon size={20} /> : <MinusIcon size={20} />}
              </button>
              <span className="qty-value">{inCart}<span className="visually-hidden"> in cart</span></span>
              <button ref={plusRef} type="button" className="qty-btn" onClick={add}
                aria-disabled={atLimit ? "true" : undefined} aria-label={`Add one more ${label}`}>
                <PlusIcon size={20} />
              </button>
            </div>
          )}
          {atLimit && <p className="product-limit">Maximum quantity: {MAX_QUANTITY}</p>}
        </div>
      </div>
    </article>
  );
}

// A11: shown while the catalog loads. Hidden from assistive tech; the
// "Loading products" text carries the state.
export function SkeletonCard() {
  return (
    <div className="product-card skeleton-card">
      <div className="product-well" />
      <div className="product-body">
        <span className="skeleton-line" style={{ width: "45%" }} />
        <span className="skeleton-line" style={{ width: "85%" }} />
        <span className="skeleton-line" style={{ width: "30%" }} />
        <span className="skeleton-pill" />
      </div>
    </div>
  );
}
