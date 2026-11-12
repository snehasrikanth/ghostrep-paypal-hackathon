import assert from "node:assert/strict";
import test from "node:test";
import { purchaseJourney } from "./purchaseJourney.ts";
import type { ReviewOrder } from "./commerce";
const order = (overrides: Partial<ReviewOrder> = {}) => ({ payment_state: "checkout_ready", mode: "sandbox", calls: [], task: null, package: { kind: "live_calls" }, ...overrides } as ReviewOrder);
test("queued requests never look like confirmed coaching or delivered sessions", () => {
  const steps = purchaseJourney(order({ payment_state: "paid", task: { status: "queued" } as ReviewOrder["task"] }));
  assert.equal(steps[1].state, "done");
  assert.equal(steps[2].state, "current");
  assert.equal(steps[3].state, "waiting");
});
test("pending capture, cancellation and refunds cannot show fulfillment as active", () => {
  for (const state of ["capture_pending", "canceled", "refunded", "refund_pending"]) {
    const steps = purchaseJourney(order({ payment_state: state }));
    assert.notEqual(steps[2].state, "done");
    assert.notEqual(steps[3].state, "done");
    assert.notEqual(steps[2].state, "current");
  }
});
test("simulations are labeled and completed calls are distinguished from confirmed appointments", () => {
  const calls = [{ status: "confirmed" }] as ReviewOrder["calls"];
  const confirmed = purchaseJourney(order({ mode: "simulated", payment_state: "paid", calls }));
  assert.equal(confirmed[1].label, "Practice payment");
  assert.equal(confirmed[2].state, "done");
  assert.equal(confirmed[3].state, "current");
  const completed = purchaseJourney(order({ payment_state: "paid", calls: [{ status: "completed" }] as ReviewOrder["calls"] }));
  assert.equal(completed[3].state, "done");
});

test("coach notes alone do not claim a live session has happened", () => {
  const steps = purchaseJourney(order({ payment_state: "paid", task: { status: "delivered" } as ReviewOrder["task"] }));
  assert.equal(steps[3].state, "waiting");
});
