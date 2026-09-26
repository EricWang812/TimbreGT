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

function Summary({ quote }) {
  return (
    <table className="summary">
      <caption className="visually-hidden">Order summary</caption>
      <thead className="visually-hidden">
        <tr><th scope="col">Item</th><th scope="col" className="amount">Amount</th></tr>
      </thead>
      <tbody>
        {quote.lines.map((line) => (
          <tr key={line.product_id}>
            <td>{line.name}<br /><span className="note">{line.quantity} × {formatCents(line.unit_cents)}</span></td>
            <td className="amount">{formatCents(line.line_cents)}</td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr><th scope="row">Subtotal</th><td className="amount">{formatCents(quote.subtotal_cents)}</td></tr>
        <tr><th scope="row">Tax</th><td className="amount">{formatCents(quote.tax_cents)}</td></tr>
        <tr>
          <th scope="row">Shipping</th>
          <td className="amount">{quote.shipping_cents === 0 ? "Free" : formatCents(quote.shipping_cents)}</td>
        </tr>
        <tr className="total"><th scope="row">Total</th><td className="amount">{formatCents(quote.total_cents)}</td></tr>
      </tfoot>
    </table>
  );
}

export default function Checkout() {
  const cart = useCart();
  const announce = useAnnounce();
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
      <div className="stack">
        <PageHeading>Checkout</PageHeading>
        <p>Your cart is empty.</p>
        <p><a className="btn btn-secondary" href="#/">Back to the shop</a></p>
      </div>
    );
  }

  const busy = step === "starting" || step === "awaiting-bank" || step === "completing";

  return (
    <>
      <div className="page-intro">
        <PageHeading>Checkout</PageHeading>
      </div>
      <div className="checkout-layout">
        <section className="panel" aria-labelledby="summary-heading">
          <h2 id="summary-heading">Your order</h2>
          {quote.status === "loading" && <p aria-busy="true">Pricing your cart…</p>}
          {quote.status === "error" && <p className="message-error" role="alert">Prices could not load. Reload the page to try again.</p>}
          {quote.status === "ready" && <Summary quote={quote} />}
        </section>

        <section className="panel stack" aria-labelledby="pay-heading">
          <h2 id="pay-heading">Payment</h2>
          <p>Your bank confirms it is you. Seaside Market only learns whether the payment went through.</p>
          {step === "not-approved" && (
            <p className="message-error">Your bank has not approved this payment. You can try again.</p>
          )}
          {step === "error" && (
            <p className="message-error">Something went wrong reaching the payment service. Please try again.</p>
          )}
          <button type="button" ref={approveRef} className="btn btn-primary btn-large btn-block"
            onClick={startApproval} disabled={quote.status !== "ready" || busy}>
            {busy ? "Waiting for your bank…" : quote.status === "ready"
              ? `Approve purchase, ${formatCents(quote.total_cents)}` : "Approve purchase"}
          </button>
          <p><a href="#/">Keep shopping</a></p>
        </section>
      </div>

      {attempt && <ApprovalWidget sessionId={attempt.sessionId} onClose={bankClosed} />}
    </>
  );
}
