import { useEffect, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import CheckoutSteps from "../components/CheckoutSteps.jsx";
import { CheckIcon } from "../components/Icons.jsx";
import { getOrder } from "../lib/api.js";
import { formatCents } from "../lib/money.js";

// A16: the check draws itself once (styles/checkout.css). Its resting state is
// fully drawn, so with motion off it is simply there. Decorative: the heading
// and the status line carry the meaning.
function ApprovedMark() {
  return (
    <svg className="receipt-mark" width="64" height="64" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <circle cx="32" cy="32" r="32" className="receipt-mark-circle" />
      <path d="M19 33.5 28 42.5 45.5 23" pathLength="1" className="receipt-mark-check" />
    </svg>
  );
}

export default function Receipt({ instructionId, products = {} }) {
  const [order, setOrder] = useState({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    getOrder(instructionId).then(
      (o) => !cancelled && setOrder({ status: "ready", ...o }),
      (err) => {
        console.error("order lookup failed", err);
        if (!cancelled) setOrder({ status: "error" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [instructionId]);

  if (order.status === "loading") return <p aria-busy="true">Loading your receipt…</p>;
  if (order.status === "error") {
    return (
      <div className="receipt">
        <PageHeading>Receipt not found</PageHeading>
        <p className="message-error" role="alert">We could not find this order.</p>
        <p><a className="btn btn-secondary" href="#/">Back to the shop</a></p>
      </div>
    );
  }

  const approved = order.status === "approved";
  return (
    <div className="receipt">
      <CheckoutSteps current={approved ? "Receipt" : "Checkout"} />
      <div className="receipt-head">
        {approved && <ApprovedMark />}
        <PageHeading>{approved ? "Thank you!" : "Order pending"}</PageHeading>
        {approved ? (
          <p className="receipt-status"><CheckIcon /> Payment approved by your bank</p>
        ) : (
          <p className="note">Your bank has not approved this order yet.</p>
        )}
      </div>

      <section className="receipt-card" aria-labelledby="receipt-items">
        <h2 id="receipt-items">Receipt</h2>
        <table className="receipt-table">
          <caption className="visually-hidden">Items purchased</caption>
          <thead className="visually-hidden">
            <tr><th scope="col">Item</th><th scope="col">Amount</th></tr>
          </thead>
          <tbody>
            {order.lines.map((line) => {
              const p = products[line.product_id];
              return (
                <tr key={line.product_id}>
                  <td>
                    <div className="receipt-item">
                      {p
                        ? <img className="receipt-thumb" src={p.image_url} alt="" width="48" height="48" />
                        : <span className="receipt-thumb" aria-hidden="true" />}
                      <span>
                        {line.name}<br />
                        <span className="receipt-unit">{line.quantity} × {formatCents(line.unit_cents)}</span>
                      </span>
                    </div>
                  </td>
                  <td className="receipt-amount">{formatCents(line.line_cents)}</td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr><th scope="row">Subtotal</th><td className="receipt-amount">{formatCents(order.subtotal_cents)}</td></tr>
            <tr><th scope="row">Tax</th><td className="receipt-amount">{formatCents(order.tax_cents)}</td></tr>
            <tr>
              <th scope="row">Shipping</th>
              <td className="receipt-amount">{order.shipping_cents === 0 ? "Free" : formatCents(order.shipping_cents)}</td>
            </tr>
            <tr className="receipt-total-row">
              <th scope="row">Total</th><td className="receipt-amount">{formatCents(order.total_cents)}</td>
            </tr>
          </tfoot>
        </table>
        {approved && (
          <p className="receipt-txn">Transaction <span className="receipt-mono">{order.transaction_id}</span></p>
        )}
      </section>

      {approved && (
        <section className="receipt-learned" aria-labelledby="merchant-learned">
          <h2 id="merchant-learned">What Seaside Market learned from your bank</h2>
          <p>This is the entire approval the store received. No score, no method, nothing about you.</p>
          <div className="receipt-code">
            <p className="receipt-code-label">Approval response</p>
            <pre className="receipt-mono">{JSON.stringify({ verified: true, transaction_id: order.transaction_id }, null, 2)}</pre>
          </div>
        </section>
      )}

      <p className="receipt-actions"><a className="btn btn-primary receipt-cta" href="#/">Continue shopping</a></p>
    </div>
  );
}
