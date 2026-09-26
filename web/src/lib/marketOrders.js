export const ORDER_STAGES = [["NOT_STARTED", "Not Started"], ["FULFILLING", "Fulfilling"], ["ORDER_COMPLETE", "Order Complete"], ["SHIPPING", "Shipping"], ["READY_FOR_PICKUP", "Ready for Pickup"]];
export const statusLabel = (status) => Object.fromEntries(ORDER_STAGES)[status] ?? status;
export const fulfillmentLabel = (order) => order.fulfillmentMethod === "PICKUP" ? "Pickup" : order.localDriver ? "Local driver" : "Shipping";
export function elapsed(since, now = Date.now()) {
  const minutes = Math.floor((now - Date.parse(since)) / 60000);
  if (!Number.isFinite(minutes) || minutes < 0) return "Time unavailable";
  if (minutes < 60) return `${minutes} min`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} hr`;
  return `${Math.floor(minutes / 1440)} days`;
}
export const orderLink = (marketId, orderId) => `#/market-dashboard/${encodeURIComponent(marketId)}/orders/${encodeURIComponent(orderId)}`;

export function attention(order) {
  const duration = order.stageSince ? ` · ${elapsed(order.stageSince)} in stage` : " · stage time unavailable";
  if (order.status === "NOT_STARTED") return `Awaiting start${duration}`;
  if (order.status === "FULFILLING") return `Being fulfilled${duration}`;
  if (order.status === "ORDER_COMPLETE" && order.fulfillmentMethod === "SHIP") return `Waiting to ship${duration}`;
  if (order.status === "READY_FOR_PICKUP") return `Awaiting pickup${duration}`;
  return null;
}
export function visibleOrders(orders, filter, sort) {
  return orders.filter((o) => filter === "ALL" || o.status === filter).sort((a, b) => {
    if (sort === "VALUE") return b.totalCents - a.totalCents || a.id.localeCompare(b.id);
    return (Date.parse(a.createdAt) - Date.parse(b.createdAt)) * (sort === "OLDEST" ? 1 : -1) || a.id.localeCompare(b.id);
  });
}
