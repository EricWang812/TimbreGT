import { useEffect, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import { CheckIcon } from "../components/Icons.jsx";
import { getOrder } from "../lib/api.js";
import { formatCents } from "../lib/money.js";

export default function Receipt({ instructionId }) {
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
      <div className="stack">
        <PageHeading>Receipt not found</PageHeading>
        <p className="message-error" role="alert">We could not find this order.</p>
        <p><a className="btn btn-secondary" href="#/">Back to the shop</a></p>
      </div>
    );
  }

  const approved = order.status === "approved";
  return (
    <div className="stack">
      <PageHeading>{approved ? "Thank you!" : "Order pending"}</PageHeading>
      {approved ? (
        <p className="status-banner"><CheckIcon /> Payment approved by your bank</p>
      ) : (
        <p className="note">Your bank has not approved this order yet.</p>
      )}

      <section className="panel stack" aria-labelledby="receipt-items">
        <h2 id="receipt-items">Receipt</h2>
        <table className="summary">
          <caption className="visually-hidden">Items purchased</caption>
          <thead className="visually-hidden">
            <tr><th scope="col">Item</th><th scope="col" className="amount">Amount</th></tr>
          </thead>
          <tbody>
            {order.lines.map((line) => (
              <tr key={line.product_id}>
                <td>{line.name}<br /><span className="note">{line.quantity} × {formatCents(line.unit_cents)}</span></td>
                <td className="amount">{formatCents(line.line_cents)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr><th scope="row">Subtotal</th><td className="amount">{formatCents(order.subtotal_cents)}</td></tr>
            <tr><th scope="row">Tax</th><td className="amount">{formatCents(order.tax_cents)}</td></tr>
            <tr>
              <th scope="row">Shipping</th>
              <td className="amount">{order.shipping_cents === 0 ? "Free" : formatCents(order.shipping_cents)}</td>
            </tr>
            <tr className="total"><th scope="row">Total</th><td className="amount">{formatCents(order.total_cents)}</td></tr>
          </tfoot>
        </table>
        {approved && <p>Transaction <span className="mono">{order.transaction_id}</span></p>}
      </section>

      {approved && (
        <section className="panel stack" aria-labelledby="merchant-learned">
          <h2 id="merchant-learned">What Seaside Market learned from your bank</h2>
          <p className="note">This is the entire approval the store received. No score, no method, nothing about you.</p>
          <pre className="mono">{JSON.stringify({ verified: true, transaction_id: order.transaction_id }, null, 2)}</pre>
        </section>
      )}

      <p><a className="btn btn-primary" href="#/">Continue shopping</a></p>
    </div>
  );
}
