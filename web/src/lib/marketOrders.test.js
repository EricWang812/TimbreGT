import { test } from "node:test";
import assert from "node:assert/strict";
import { visibleOrders, attention, elapsed } from "./marketOrders.js";
test("filters and sorts persisted order-shaped records without mutating input", () => {
  const orders = [{id:"a", status:"SHIPPING", totalCents:10, createdAt:"2026-01-01"}, {id:"b", status:"FULFILLING", totalCents:20, createdAt:"2026-01-02"}];
  assert.deepEqual(visibleOrders(orders, "ALL", "VALUE").map(o => o.id), ["b", "a"]);
  assert.equal(visibleOrders(orders, "FULFILLING", "OLDEST")[0].id, "b");
  assert.equal(orders[0].id, "a");
  assert.equal(elapsed("invalid"), "Time unavailable");
  assert.match(attention({status:"ORDER_COMPLETE", fulfillmentMethod:"SHIP"}), /Waiting to ship/);
  assert.doesNotMatch(attention({status:"READY_FOR_PICKUP"}), /late|deadline/);
});
