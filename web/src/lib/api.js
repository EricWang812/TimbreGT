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
    credentials: "include",
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
  if (res.status === 204) return null;
  return res.json();
}

const toItems = (lines) => lines.map((l) => ({ product_id: l.productId, quantity: l.quantity }));

export const getHealth = () => request("/healthz");
export const getCatalog = () => request("/catalog");
export const getStoreInfo = () => request("/store");
export const getMarketBranding = (marketId) => request(`/markets/${encodeURIComponent(marketId)}`);
export const getStorefrontMarkets = () => request("/storefront/markets");
export const getStorefrontProducts = (marketId) => request(`/storefront/markets/${encodeURIComponent(marketId)}/products`);
export const quoteCart = (lines, fulfillmentMethod) => request("/cart/quote", { method: "POST", body: fulfillmentMethod ? { items: toItems(lines), fulfillmentMethod } : { items: toItems(lines) } });
// A signed-in buyer's fulfillment ({method, shippingAddressId}) makes the purchase
// part of their order history; guests send none.
export const confirmCheckout = (lines, fulfillment) => request("/checkout/confirm", { method: "POST", body: fulfillment ? { items: toItems(lines), fulfillment } : { items: toItems(lines) } });
export const getFulfillmentOptions = (marketId) => request(`/buyer/markets/${encodeURIComponent(marketId)}/fulfillment-options`);
// Returns exactly {verified, transaction_id}: all the merchant ever learns (§2.5).
export const completeCheckout = (instructionId) =>
  request("/checkout/complete", { method: "POST", body: { instruction_id: instructionId } });
export const getOrder = (instructionId) => request(`/orders/${instructionId}`);
export const getBuyerAccount = () => request("/buyer-auth/me");
export const getBuyerSession = () => request("/buyer-auth/session");
export const getBuyerOrders = () => request("/buyer/markets/orders");
export const getBuyerOrder = (orderId) => request(`/buyer/markets/orders/${encodeURIComponent(orderId)}`);
export const buyAgain = (orderId) => request(`/buyer/markets/orders/${encodeURIComponent(orderId)}/buy-again`, { method: "POST" });
export const getMarketOwnerAccount = () => request("/market-auth/me");
export const getOwnedMarkets = () => request("/markets/mine");
export const getMarketOrders = (marketId) => request(`/markets/${encodeURIComponent(marketId)}/orders`);
export const getMarketOwnerSession = () => request("/market-auth/session");
export const logoutBuyer = () => request("/buyer-auth/logout", { method: "POST" });
export const logoutMarketOwner = () => request("/market-auth/logout", { method: "POST" });

async function shoppingRequest(path, body, signal, json = false, marketId) {
  const res = await fetch(`${MERCHANT_URL}${path}${marketId ? `?marketId=${encodeURIComponent(marketId)}` : ""}`, {
    method: "POST", signal, body: json ? JSON.stringify(body) : body,
    headers: json ? { "Content-Type": "application/json" } : {},
  });
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail, () => null);
    throw new ApiError(typeof detail === "string" ? detail : "Shopping could not understand that. Use the product buttons or try typing.", res.status);
  }
  return res.json();
}
export const shoppingText = (text, signal, marketId) => shoppingRequest("/shopping/text", { text }, signal, true, marketId);
export const shoppingVoice = (wav, signal, marketId) => {
  const body = new FormData();
  body.append("audio", wav, "shopping.wav");
  return shoppingRequest("/shopping/voice", body, signal, false, marketId);
};

export const transcribeAgenticShopping = (wav, signal) => {
  const body = new FormData();
  body.append("audio", wav, "agentic-shopping.wav");
  return shoppingRequest("/agentic-shopping/transcribe", body, signal);
};
export const extractAgenticIntent = (transcript, signal) =>
  shoppingRequest("/agentic-shopping/intent", { transcript }, signal, true);
export const startAgenticClarifications = (intent, signal) =>
  shoppingRequest("/agentic-shopping/clarifications", intent, signal, true);
export const answerAgenticClarification = (state, answer, signal) =>
  shoppingRequest("/agentic-shopping/clarifications/answer", { state, answer }, signal, true);
export const finalizeAgenticShopping = (state, signal) =>
  shoppingRequest("/agentic-shopping/finalize", state, signal, true);

// The agent returns the complete server-priced cart. The caller applies
// `items` to the existing CartProvider only when status is "cart_ready".
export const prepareAgenticCart = (finalizedRequest, lines, signal) =>
  shoppingRequest(
    "/agentic-shopping/commerce/prepare-cart",
    { finalizedRequest, existingItems: toItems(lines) },
    signal,
    true,
  );

// A whole basket: several named items and meals (api/basket.py). `prepare`
// returns a server-priced proposal; the caller applies `items` to the
// CartProvider only when the shopper has seen it (or it needs no review).
export const extractAgenticBasket = (transcript, signal, marketId) =>
  shoppingRequest("/agentic-shopping/basket/intent", { transcript }, signal, true, marketId);
export const startBasketClarifications = (extraction, signal, marketId) =>
  shoppingRequest("/agentic-shopping/basket/clarifications", extraction, signal, true, marketId);
export const answerBasketClarification = (state, answer, signal, marketId) =>
  shoppingRequest("/agentic-shopping/basket/clarifications/answer", { state, answer }, signal, true, marketId);
export const prepareAgenticBasket = (state, lines, skip, signal, marketId) =>
  shoppingRequest(
    "/agentic-shopping/basket/prepare",
    { state, existingItems: toItems(lines), skip },
    signal,
    true, marketId,
  );

export const getCartProducts = (productIds) => request("/storefront/cart-products", { method: "POST", body: { productIds } });

export const updateMarketOrderStatus = (marketId, orderId, status) => request(`/markets/${encodeURIComponent(marketId)}/orders/${encodeURIComponent(orderId)}/status`, { method: "PATCH", body: { status } });

export const getMarketAnalytics = (marketId, period) => request(`/markets/${encodeURIComponent(marketId)}/analytics?period=${encodeURIComponent(period)}`);

export const getMarketOperations = (marketId) => request(`/markets/${encodeURIComponent(marketId)}/operations`);

export const getMarketInsights = (marketId) => request(`/markets/${encodeURIComponent(marketId)}/insights`);
export const explainMarketInsights = (marketId) => request(`/markets/${encodeURIComponent(marketId)}/insights/explanation`, { method: "POST" });

// Account sessions are HttpOnly cookies set by the merchant; the browser never sees a token.
export const loginBuyer = (email, password) => request("/buyer-auth/login", { method: "POST", body: { email, password } });
export const registerBuyer = (email, password) => request("/buyer-auth/register", { method: "POST", body: { email, password } });
export const loginMarketOwner = (email, password) => request("/market-auth/login", { method: "POST", body: { email, password } });
export const registerMarketOwner = (email, password) => request("/market-auth/register", { method: "POST", body: { email, password } });
export const getBuyerAddresses = () => request("/buyer/addresses");
export const createBuyerAddress = (address) => request("/buyer/addresses", { method: "POST", body: address });
export const createMarket = (name) => request("/markets", { method: "POST", body: { name } });

// Seller product management (owner session). Prices are dollars; the server stores cents.
const productsPath = (marketId) => `/markets/${encodeURIComponent(marketId)}/products`;
export const getMarketProducts = (marketId) => request(productsPath(marketId));
export const createMarketProduct = (marketId, product) => request(productsPath(marketId), { method: "POST", body: product });
export const updateMarketProduct = (marketId, productId, changes) => request(`${productsPath(marketId)}/${encodeURIComponent(productId)}`, { method: "PATCH", body: changes });
export const deleteMarketProduct = (marketId, productId) => request(`${productsPath(marketId)}/${encodeURIComponent(productId)}`, { method: "DELETE" });
export const getPickupSettings = (marketId) => request(`/markets/${encodeURIComponent(marketId)}/pickup-settings`);
export const updatePickupSettings = (marketId, changes) => request(`/markets/${encodeURIComponent(marketId)}/pickup-settings`, { method: "PATCH", body: changes });
export const getShippingSettings = (marketId) => request(`/markets/${encodeURIComponent(marketId)}/shipping-settings`);
export const updateShippingSettings = (marketId, changes) => request(`/markets/${encodeURIComponent(marketId)}/shipping-settings`, { method: "PATCH", body: changes });
