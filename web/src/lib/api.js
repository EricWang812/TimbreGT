// Merchant API client. The storefront talks to the merchant only. The issuer
// challenge widget has its own client (src/issuer/issuerApi.js) and must never
// import this file, and this file must never call the issuer.
const MERCHANT_URL = __MERCHANT_URL__;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(`${MERCHANT_URL}${path}`, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail, () => null);
    throw new ApiError(
      `merchant ${method} ${path} failed with HTTP ${res.status}${detail ? `: ${JSON.stringify(detail)}` : ""}`,
      res.status,
    );
  }
  return res.json();
}

const toItems = (lines) => lines.map((l) => ({ product_id: l.productId, quantity: l.quantity }));

export const getHealth = () => request("/healthz");
export const getCatalog = () => request("/catalog");
export const getStoreInfo = () => request("/store");
export const quoteCart = (lines) => request("/cart/quote", { method: "POST", body: { items: toItems(lines) } });
export const confirmCheckout = (lines) => request("/checkout/confirm", { method: "POST", body: { items: toItems(lines) } });
// Returns exactly {verified, transaction_id}: all the merchant ever learns (§2.5).
export const completeCheckout = (instructionId) =>
  request("/checkout/complete", { method: "POST", body: { instruction_id: instructionId } });
export const getOrder = (instructionId) => request(`/orders/${instructionId}`);

async function shoppingRequest(path, body, signal, json = false) {
  const res = await fetch(`${MERCHANT_URL}${path}`, {
    method: "POST", signal, body: json ? JSON.stringify(body) : body,
    headers: json ? { "Content-Type": "application/json" } : {},
  });
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail, () => null);
    throw new ApiError(typeof detail === "string" ? detail : "Shopping could not understand that. Use the product buttons or try typing.", res.status);
  }
  return res.json();
}
export const shoppingText = (text, signal) => shoppingRequest("/shopping/text", { text }, signal, true);
export const shoppingVoice = (wav, signal) => {
  const body = new FormData();
  body.append("audio", wav, "shopping.wav");
  return shoppingRequest("/shopping/voice", body, signal);
};
