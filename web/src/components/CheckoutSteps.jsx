// "Cart, Checkout, Receipt" progress. The current step is bold and underlined
// (styles/checkout.css), not only colored, and carries aria-current="step".
const STEPS = ["Cart", "Checkout", "Receipt"];

export default function CheckoutSteps({ current }) {
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
