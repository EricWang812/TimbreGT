// Native <dialog> + showModal(): focus is trapped inside, Escape closes it,
// and focus returns to the Cart button on close, all without custom code.
import { useEffect, useRef } from "react";
import { MAX_QUANTITY, itemCountText, useCart } from "../lib/cart.jsx";
import { useAnnounce } from "../lib/announce.jsx";
import { formatCents } from "../lib/money.js";
import { navigate } from "../lib/router.js";
import { CloseIcon, MinusIcon, PlusIcon } from "./Icons.jsx";

export default function CartDrawer({ open, onClose, products }) {
  const dialogRef = useRef(null);
  const keepShoppingRef = useRef(null);
  const cart = useCart();
  const announce = useAnnounce();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

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
      // The focused button disappears with its line. Move to the next line's
      // Remove button (the one that slid into this position), so removing
      // several items does not mean re-tabbing from the top each time.
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

  return (
    <dialog ref={dialogRef} className="cart-dialog" aria-labelledby="cart-title" onClose={onClose}>
      <div className="drawer">
        <div className="drawer-header">
          <h2 id="cart-title" tabIndex={-1}>Your cart</h2>
          <button type="button" className="btn btn-secondary" onClick={onClose} aria-label="Close cart">
            <CloseIcon size={20} />
          </button>
        </div>

        <div className="drawer-body">
          {cart.lines.length === 0 ? (
            <p className="note">Your cart is empty.</p>
          ) : (
            <ul className="cart-lines">
              {cart.lines.map(({ productId, quantity }, index) => {
                const p = products[productId];
                const name = p ? p.name : "Loading item…";
                return (
                  <li key={productId} className="cart-line">
                    {p ? <img src={p.image_url} alt="" width="64" height="64" /> : <span aria-hidden="true" />}
                    <div>
                      {p && <p className="product-brand">{p.brand}</p>}
                      <h3>{name}</h3>
                      {p && <p>{formatCents(p.price_cents * quantity)}</p>}
                      <div className="stepper">
                        <button type="button" className="btn btn-secondary"
                          onClick={() => change(productId, quantity - 1, index)}
                          aria-label={`Remove one ${name}`}>
                          <MinusIcon size={20} />
                        </button>
                        {/* A plain span: the app-wide live region already
                            announces the change, and <output> would say it twice. */}
                        <span className="quantity" aria-label={`Quantity ${quantity}`}>{quantity}</span>
                        <button type="button" className="btn btn-secondary"
                          onClick={() => change(productId, quantity + 1, index)}
                          disabled={quantity >= MAX_QUANTITY}
                          aria-label={`Add one ${name}`}>
                          <PlusIcon size={20} />
                        </button>
                        <button type="button" className="btn btn-secondary" data-remove
                          onClick={() => change(productId, 0, index)}
                          aria-label={`Remove ${name} from cart`}>
                          Remove
                        </button>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="drawer-footer">
          <p>
            <strong>Subtotal: {pending ? "calculating…" : formatCents(subtotal)}</strong>{" "}
            <span className="note">Tax and shipping at checkout.</span>
          </p>
          <button type="button" className="btn btn-primary btn-large btn-block"
            onClick={checkout} disabled={cart.lines.length === 0}>
            Go to checkout
          </button>
          <button type="button" ref={keepShoppingRef} className="btn btn-secondary btn-block" onClick={onClose}>
            Keep shopping
          </button>
        </div>
      </div>
    </dialog>
  );
}
