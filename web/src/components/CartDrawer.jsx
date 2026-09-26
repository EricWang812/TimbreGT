// Native <dialog> + showModal(): focus is trapped inside, Escape closes it,
// and focus returns to the Cart button on close, all without custom code.
// Open and close animate in CSS only (styles/checkout.css, A6/A7); nothing
// here waits for a transition, so the drawer behaves the same with motion off.
import { useEffect, useRef, useState } from "react";
import { MAX_QUANTITY, itemCountText, useCart } from "../lib/cart.jsx";
import { useAnnounce } from "../lib/announce.jsx";
import { quoteCart } from "../lib/api.js";
import { formatCents } from "../lib/money.js";
import { navigate } from "../lib/router.js";
import { CheckIcon, CloseIcon, MicIcon, MinusIcon, PlusIcon, TrashIcon } from "./Icons.jsx";

const VOICE_BUTTON_TEXT = "Speak an item";
const VOICE_FOCUS_MAX_FRAMES = 90;  // about 1.5s: long enough for the shop route and catalog to mount

// The voice panel belongs to another component, so find its button by its
// visible text; fall back to the panel heading, which is made focusable.
function findVoiceTarget() {
  const main = document.getElementById("main-content");
  if (!main) return null;
  const button = [...main.querySelectorAll("button")]
    .find((b) => b.textContent.trim().startsWith(VOICE_BUTTON_TEXT) && !b.disabled);
  if (button) return button;
  const heading = document.getElementById("voice-shopping-title");
  if (heading && !heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
  return heading;
}

function countLabel(count) {
  return count === 1 ? "1 item" : `${count} items`;
}

// A14: the threshold comes from the merchant's quote (free_shipping_min_cents),
// never from a copy in the web app. The bar is decorative; the sentence says it.
function FreeDeliveryMeter({ subtotal, threshold }) {
  const remaining = Math.max(threshold - subtotal, 0);
  const ratio = threshold > 0 ? Math.min(subtotal / threshold, 1) : 1;
  return (
    <div className="drawer-meter">
      {remaining > 0 ? (
        <p className="drawer-meter-text">Add {formatCents(remaining)} more for free delivery</p>
      ) : (
        <p className="drawer-meter-text drawer-meter-done"><CheckIcon size={20} /> Your order ships free</p>
      )}
      <div className="drawer-meter-track" aria-hidden="true">
        <div className="drawer-meter-fill" style={{ transform: `scaleX(${ratio})` }} />
      </div>
    </div>
  );
}

export default function CartDrawer({ open, onClose, products }) {
  const dialogRef = useRef(null);
  const keepShoppingRef = useRef(null);
  const cart = useCart();
  const announce = useAnnounce();
  const [freeShippingMin, setFreeShippingMin] = useState(null);
  const hasLines = cart.lines.length > 0;

  useEffect(() => {
    const dialog = dialogRef.current;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  // Ask the merchant for the free-delivery threshold once the drawer shows a
  // cart. The quote needs at least one line, so an empty cart skips it.
  useEffect(() => {
    if (!open || !hasLines || freeShippingMin !== null) return;
    let cancelled = false;
    quoteCart(cart.lines).then(
      (q) => {
        if (cancelled) return;
        // A missing or malformed threshold hides the meter. It must never fall
        // through to "Your order ships free", which would be a false promise.
        if (Number.isInteger(q.free_shipping_min_cents) && q.free_shipping_min_cents > 0) {
          setFreeShippingMin(q.free_shipping_min_cents);
        } else {
          console.error("free-delivery threshold missing from the quote", q.free_shipping_min_cents);
        }
      },
      (err) => console.error("free-delivery threshold unavailable (quote failed)", err),
    );
    return () => {
      cancelled = true;
    };
  }, [open, hasLines, freeShippingMin]);  // cart.lines left out on purpose: the threshold does not depend on them

  // Lines render even before the catalog arrives (the cart is restored from
  // sessionStorage first), so checkout never depends on the catalog loading.
  const pending = cart.lines.some((l) => !products[l.productId]);
  // Display estimate from catalog prices; checkout re-prices on the server.
  const subtotal = cart.lines.reduce(
    (sum, l) => sum + (products[l.productId]?.price_cents ?? 0) * l.quantity, 0);
  const nameOf = (productId) => {
    const p = products[productId];
    return p ? `${p.brand} ${p.name}` : "this item";
  };

  function change(productId, quantity, index) {
    cart.setQuantity(productId, quantity);
    const total = cart.count - cart.quantityOf(productId) + Math.max(quantity, 0);
    announce(quantity <= 0
      ? `Removed ${nameOf(productId)}. ${itemCountText(total)}.`
      : `${nameOf(productId)}: quantity ${quantity}. ${itemCountText(total)}.`);
    if (quantity <= 0) {
      // The focused button disappears with its line (instantly: lines have no
      // exit animation). Move to the next line's Remove button (the one that
      // slid into this position), so removing several items does not mean
      // re-tabbing from the top each time.
      requestAnimationFrame(() => {
        const removes = dialogRef.current.querySelectorAll("[data-remove]");
        const next = removes[Math.min(index, removes.length - 1)];
        (next ?? keepShoppingRef.current)?.focus();
      });
    }
  }

  function checkout() {
    onClose();
    navigate("/checkout");
  }

  // Close, then move focus to the voice panel. The dialog hands focus back to
  // the Cart button when it closes, so wait until it has closed (and, from
  // another page, until the shop has mounted) before focusing.
  function shopByVoice() {
    onClose();
    if (!findVoiceTarget()) navigate("/");
    let frames = 0;
    const attempt = () => {
      const target = dialogRef.current?.open ? null : findVoiceTarget();
      if (target) target.focus();
      else if (++frames < VOICE_FOCUS_MAX_FRAMES) requestAnimationFrame(attempt);
    };
    requestAnimationFrame(attempt);
  }

  return (
    <dialog ref={dialogRef} className="drawer-dialog" aria-labelledby="cart-title" onClose={onClose}>
      <div className="drawer-panel">
        <div className="drawer-top">
          <h2 id="cart-title" tabIndex={-1}>
            Your cart <span className="drawer-count">({countLabel(cart.count)})</span>
          </h2>
          <button type="button" className="btn btn-secondary drawer-close" onClick={onClose} aria-label="Close cart">
            <CloseIcon size={20} />
          </button>
        </div>

        {hasLines && !pending && freeShippingMin !== null && (
          <FreeDeliveryMeter subtotal={subtotal} threshold={freeShippingMin} />
        )}

        <div className="drawer-scroll">
          {!hasLines ? (
            <div className="drawer-empty">
              <p>Your cart is empty. Name an item out loud and we will find it for you.</p>
              <button type="button" className="btn btn-primary drawer-cta" onClick={shopByVoice}>
                <MicIcon size={22} /> Shop by voice
              </button>
            </div>
          ) : (
            <ul className="drawer-lines">
              {cart.lines.map(({ productId, quantity }, index) => {
                const p = products[productId];
                const name = p ? p.name : "Loading item…";
                return (
                  <li key={productId} className="drawer-line">
                    {p
                      ? <img className="drawer-thumb" src={p.image_url} alt="" width="64" height="64" />
                      : <span className="drawer-thumb" aria-hidden="true" />}
                    <div className="drawer-line-info">
                      {p && <p className="drawer-line-brand">{p.brand}</p>}
                      <h3 className="drawer-line-name">{name}</h3>
                      {p && <p className="drawer-line-unit">{quantity} × {formatCents(p.price_cents)}</p>}
                    </div>
                    <p className="drawer-line-total">{p ? formatCents(p.price_cents * quantity) : ""}</p>
                    <div className="drawer-line-controls">
                      <div className="drawer-stepper">
                        <button type="button" className="drawer-step-btn"
                          onClick={() => change(productId, quantity - 1, index)}
                          aria-label={`Remove one ${name}`}>
                          {quantity === 1 ? <TrashIcon size={20} /> : <MinusIcon size={20} />}
                        </button>
                        {/* A plain span: the app-wide live region already
                            announces the change, and <output> would say it twice. */}
                        <span className="drawer-qty" aria-label={`Quantity ${quantity}`}>{quantity}</span>
                        <button type="button" className="drawer-step-btn"
                          onClick={() => change(productId, quantity + 1, index)}
                          disabled={quantity >= MAX_QUANTITY}
                          aria-label={`Add one ${name}`}>
                          <PlusIcon size={20} />
                        </button>
                      </div>
                      <button type="button" className="drawer-remove" data-remove
                        onClick={() => change(productId, 0, index)}
                        aria-label={`Remove ${name} from cart`}>
                        Remove
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="drawer-bottom">
          {hasLines && (
            <>
              <p className="drawer-subtotal">
                <span>Subtotal</span>
                <span className="drawer-subtotal-amount">{pending ? "calculating…" : formatCents(subtotal)}</span>
              </p>
              <p className="note">Tax and shipping at checkout.</p>
              <button type="button" className="btn btn-primary btn-block drawer-cta" onClick={checkout}>
                Go to checkout
              </button>
            </>
          )}
          <button type="button" ref={keepShoppingRef} className="btn btn-secondary btn-block drawer-secondary"
            onClick={onClose}>
            Keep shopping
          </button>
        </div>
      </div>
    </dialog>
  );
}
