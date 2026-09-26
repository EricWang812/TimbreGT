// All amounts travel as integer cents; this is the only place they become text.
const USD = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function formatCents(cents) {
  return USD.format(cents / 100);
}
