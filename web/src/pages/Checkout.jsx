// Checkout: the merchant prices the cart, then hands the shopper to their
// bank's widget. When the widget closes, the merchant asks the issuer and
// learns only {verified, transaction_id} (§2.5).
import { useEffect, useRef, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import ApprovalWidget from "../issuer/ApprovalWidget.jsx";
import { completeCheckout, confirmCheckout, quoteCart } from "../lib/api.js";
import { useAnnounce } from "../lib/announce.jsx";
import { useCart } from "../lib/cart.jsx";
import { formatCents } from "../lib/money.js";
import { navigate } from "../lib/router.js";

const STEPS = ["Cart", "Checkout", "Receipt"];
const WIDE_QUERY = "(min-width: 900px)";

// Two layouts with different reading orders (items first on wide screens,
// the total and Approve first on phones), so the DOM order follows the
// layout instead of CSS `order` reshuffling what a screen reader hears.
function useWide() {
  const [wide, setWide] = useState(() => window.matchMedia(WIDE_QUERY).matches);
  useEffect(() => {
    const mql = window.matchMedia(WIDE_QUERY);
    const onChange = () => setWide(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return wide;
}

function Steps({ current }) {
  return (
    <ol className="checkout-steps" aria-label="Checkout steps">
      {STEPS.map((label, i) => (
        <li key={label} aria-current={label === current ? "step" : undefined}>
          <span className="checkout-step-num" aria-hidden="true">{i + 1}</span>
          <span className="checkout-step-label">{label}</span>
        </li>
      ))}
    </ol>
  );
}

// Rows come from the server quote once it is ready (the prices that will be
// charged); until then, from the cart itself, without prices.
function ItemList({ quote, lines, products }) {
  const rows = quote.status === "ready"
    ? quote.lines.map((l) => ({
      id: l.product_id, name: l.name, quantity: l.quantity, unit: l.unit_cents, total: l.line_cents,
    }))
    : lines.map((l) => ({ id: l.productId, name: products[l.productId]?.name, quantity: l.quantity }));
  return (
    <ul className="checkout-lines">
      {rows.map((row) => {
        const p = products[row.id];
        return (
          <li key={row.id} className="checkout-line">
            {p
              ? <img className="checkout-thumb" src={p.image_url} alt="" width="64" height="64" />
              : <span className="checkout-thumb" aria-hidden="true" />}
            <div className="checkout-line-info">
              {p && <p className="checkout-line-brand">{p.brand}</p>}
              <p className="checkout-line-name">{row.name ?? "Loading item…"}</p>
              <p className="checkout-line-unit">
                {row.unit === undefined ? `Quantity ${row.quantity}` : `${row.quantity} × ${formatCents(row.unit)}`}
              </p>
            </div>
            <p className="checkout-line-total">{row.total === undefined ? "" : formatCents(row.total)}</p>
          </li>
        );
      })}
    </ul>
  );
}

function Totals({ quote }) {
  return (
    <table className="checkout-totals">
      <caption className="visually-hidden">Order totals</caption>
      <tbody>
        <tr><th scope="row">Subtotal</th><td>{formatCents(quote.subtotal_cents)}</td></tr>
        <tr><th scope="row">Tax</th><td>{formatCents(quote.tax_cents)}</td></tr>
        <tr>
          <th scope="row">Shipping</th>
          <td>{quote.shipping_cents === 0 ? "Free" : formatCents(quote.shipping_cents)}</td>
        </tr>
        <tr className="checkout-total-row"><th scope="row">Total</th><td>{formatCents(quote.total_cents)}</td></tr>
      </tbody>
    </table>
  );
}

export default function Checkout({ products = {} }) {
  const cart = useCart();
  const announce = useAnnounce();
  const wide = useWide();
  const [quote, setQuote] = useState({ status: "loading" });
  const [attempt, setAttempt] = useState(null);       // {instructionId, sessionId} while the bank widget is open
  const [step, setStep] = useState("ready");          // ready | starting | awaiting-bank | completing | not-approved | error
  const cartKey = JSON.stringify(cart.lines);         // re-quote when the cart's contents change, not its identity
  const approveRef = useRef(null);

  // The dialog cannot return focus to the Approve button (it was disabled
  // while the bank widget was open), so put it back explicitly for a retry.
  useEffect(() => {
    if (step === "not-approved" || step === "error") approveRef.current?.focus();
  }, [step]);

  useEffect(() => {
    if (cart.lines.length === 0) return;
    let cancelled = false;
    setQuote({ status: "loading" });
    quoteCart(cart.lines).then(
      (q) => !cancelled && setQuote({ status: "ready", ...q }),
      (err) => {
        console.error("quote failed", err);
        if (!cancelled) setQuote({ status: "error" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [cartKey]);

  async function startApproval() {
    // Every attempt opens a fresh order and bank session, so an expired or
    // abandoned one can never trap the shopper (non-negotiable §2.4).
    setStep("starting");
    try {
      const order = await confirmCheckout(cart.lines);
      setAttempt({ instructionId: order.instruction_id, sessionId: order.session_id });
      setStep("awaiting-bank");
    } catch (err) {
      console.error("checkout confirm failed", err);
      setStep("error");
      announce("Checkout could not start. Please try again.", { assertive: true });
    }
  }

  async function bankClosed() {
    const { instructionId } = attempt;
    setAttempt(null);
    setStep("completing");
    try {
      const result = await completeCheckout(instructionId);
      if (result.verified) {
        cart.clear();
        announce("Payment approved.");
        navigate(`/receipt/${instructionId}`);
      } else {
        setStep("not-approved");
        announce("Your bank has not approved this payment. You can try again.", { assertive: true });
      }
    } catch (err) {
      console.error("checkout complete failed", err);
      setStep("error");
      announce("We could not confirm the payment. Please try again.", { assertive: true });
    }
  }

  if (cart.lines.length === 0) {
    return (
      <div className="checkout-empty">
        <PageHeading>Checkout</PageHeading>
        <p>Your cart is empty.</p>
        <p><a className="btn btn-secondary" href="#/">Back to the shop</a></p>
      </div>
    );
  }

  const busy = step === "starting" || step === "awaiting-bank" || step === "completing";
  const itemsLabel = cart.count === 1 ? "1 item" : `${cart.count} items`;
  const itemList = <ItemList quote={quote} lines={cart.lines} products={products} />;

  return (
    <>
      <div className="checkout-intro">
        <Steps current="Checkout" />
        <PageHeading>Checkout</PageHeading>
      </div>
      <div className="checkout-grid">
        {wide && (
          <section className="checkout-card checkout-items" aria-labelledby="items-heading">
            <h2 id="items-heading">Your items</h2>
            {itemList}
          </section>
        )}

        <section className="checkout-card checkout-pay" aria-labelledby="pay-heading">
          <h2 id="pay-heading">Order summary</h2>
          {quote.status === "loading" && <p aria-busy="true">Pricing your cart…</p>}
          {quote.status === "error" && <p className="message-error" role="alert">Prices could not load. Reload the page to try again.</p>}
          {quote.status === "ready" && <Totals quote={quote} />}
          <p className="checkout-privacy">
            Your bank confirms it is you. Seaside Market only learns whether the payment went through.
          </p>
          {step === "not-approved" && (
            <p className="message-error">Your bank has not approved this payment. You can try again.</p>
          )}
          {step === "error" && (
            <p className="message-error">Something went wrong reaching the payment service. Please try again.</p>
          )}
          <button type="button" ref={approveRef} className="btn btn-primary btn-block checkout-cta"
            onClick={startApproval} disabled={quote.status !== "ready" || busy}>
            {busy ? "Waiting for your bank…" : quote.status === "ready"
              ? `Approve purchase, ${formatCents(quote.total_cents)}` : "Approve purchase"}
          </button>
          <p className="checkout-back"><a href="#/">Keep shopping</a></p>
        </section>

        {!wide && (
          <section className="checkout-card checkout-items" aria-labelledby="items-heading">
            <h2 id="items-heading" className="visually-hidden">Your items</h2>
            <details className="checkout-details">
              <summary>Show {itemsLabel}</summary>
              {itemList}
            </details>
          </section>
        )}
      </div>

      {attempt && <ApprovalWidget sessionId={attempt.sessionId} onClose={bankClosed} />}
    </>
  );
}
