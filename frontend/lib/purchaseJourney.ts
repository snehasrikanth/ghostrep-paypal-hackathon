import type { ReviewOrder } from "./commerce";
export type PurchaseStep = { label: string; detail: string; state: "done" | "current" | "waiting" | "stopped" };
export function purchaseJourney(order: ReviewOrder): PurchaseStep[] {
  const paid = order.payment_state === "paid";
  const refunded = order.payment_state === "refunded";
  const pendingRefund = order.payment_state === "refund_pending";
  const canceled = order.payment_state === "canceled";
  const live = order.package.kind === "live_calls";
  const delivered = live ? order.calls.length > 0 && order.calls.every(c => c.status === "completed") : order.task?.status === "delivered";
  const confirmed = order.calls.some(c => ["confirmed", "completed"].includes(c.status));
  const simulation = order.mode === "simulated";
  return [
    { label: order.plan_review ? "Plan & preferences saved" : "Service & sharing saved", detail: "Your approved scope and fixed price are attached to this order.", state: "done" },
    { label: refunded ? "Refund confirmed" : pendingRefund ? "Refund pending" : simulation ? "Practice payment" : "PayPal payment",
      detail: refunded ? "The payment was refunded; remaining service is canceled." : pendingRefund ? "Delivery is paused while the refund is verified." : paid ? (simulation ? "Practice checkout completed. No money was charged." : "Your payment is confirmed.") : canceled ? "Checkout canceled. No service was released." : order.payment_state === "capture_pending" ? "Awaiting provider confirmation. Service stays locked." : "Complete checkout to send your request.",
      state: refunded || canceled ? "stopped" : pendingRefund ? "current" : paid ? "done" : "current" },
    { label: live ? "Coach & time confirmation" : order.package.kind === "ai_report" ? "Report preparation" : "Expert review",
      detail: refunded || pendingRefund ? "Paused or canceled by the payment state." : !paid ? "Starts after confirmed payment." : live ? (confirmed ? "A coach has confirmed a session time." : "Request queued. Coach matching and appointment time need confirmation.") : delivered ? "Your review is available below." : "Your request is in the coach inbox.",
      state: refunded || pendingRefund || canceled ? "stopped" : paid && (confirmed || delivered) ? "done" : paid ? "current" : "waiting" },
    { label: live ? "Session & follow-up" : "Review delivered", detail: delivered ? "The purchased review or session has been delivered." : live ? "Join only through a confirmed session link; follow-up notes stay on this receipt." : "Only approved feedback or the purchased report appears here.",
      state: refunded || pendingRefund || canceled ? "stopped" : delivered ? "done" : paid && confirmed ? "current" : "waiting" },
  ];
}
