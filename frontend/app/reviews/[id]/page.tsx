"use client";
import { serviceText } from "@/lib/commerceCopy";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, Clock3 } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { ModeBadge } from "@/components/reviews/ReviewPrimitives";
import { CallSchedule } from "@/components/reviews/CallSchedule";
import { ReviewReplay } from "@/components/reviews/ReviewReplay";
import { PurchaseJourney } from "@/components/reviews/PurchaseJourney";
import { PlanReviewSummary } from "@/components/reviews/PlanReviewSummary";
import { SavedSuggestion } from "@/components/reviews/SavedSuggestion";
import { PayPalSdkCheckout } from "@/components/reviews/PayPalSdkCheckout";
import { supportOfferAppropriate } from "@/lib/coachChat";
import { commerceRequest, stateLabel, usd, type ReviewOrder } from "@/lib/commerce";

function titleFor(order: ReviewOrder) {
  if (order.plan_review) return "Your live coach plan review.";
  if (order.package.family === "agentic") {
    if (order.package.kind === "ai_report") return order.task?.status === "delivered" ? "Your AI technique review." : "Your technique report checkout.";
    if (order.package.kind === "live_calls") return "Your coaching session request.";
    return "Your expert video review request.";
  }
  if (order.package.kind === "live_calls") {
    return order.calls.some(c => c.status === "confirmed") ? "Your live coaching session." : "Your live coaching.";
  }
  return "Your saved coach review.";
}

export default function ReceiptPage() {
  const { id } = useParams<{ id: string }>();
  const [order, setOrder] = useState<ReviewOrder | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [retry, setRetry] = useState(0);
  const onSdkError = useCallback((message: string) => setError(message), []);
  useEffect(() => {
    let alive = true;
    commerceRequest<ReviewOrder>(`/api/payments/orders/${id}`).catch(() => commerceRequest<ReviewOrder>(`/reviews/orders/${id}`)).then(o => {
      if (!alive) return;
      setOrder(o); setError("");
      const result = new URLSearchParams(window.location.search).get("paypal");
      if (result === "approved") setNotice("You returned from PayPal. Confirm payment below so the server can verify and capture it. This return link alone is not proof of payment.");
      if (result === "canceled") setNotice("You returned through the cancellation link. Choose Cancel checkout below to record the cancellation, or reconcile to check the provider’s current status.");
    }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [id, retry]);
  async function action(path: string, body: unknown = {}) {
    setBusy(true); setError("");
    try {
      const base = order?.package.family === "agentic" ? "/api/payments" : "/reviews";
      setOrder(await commerceRequest<ReviewOrder>(`${base}/orders/${id}/${path}`, body));
      setNotice("");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update the order."); }
    finally { setBusy(false); }
  }
  const paid = order && ["paid", "refund_pending", "refunded"].includes(order.payment_state);
  const canCheckout = order && !paid && !["canceled", "capture_pending"].includes(order.payment_state);
  const agentic = order?.package.family === "agentic";
  return <AppShell>
    <Link href={order?.plan_review ? `/workouts/${encodeURIComponent(order.plan_review.plan_id)}` : order?.sharing.recording_ids[0] ? `/reviews?recording=${order.sharing.recording_ids[0]}` : "/reviews"} className="inline-flex min-h-11 items-center gap-2 text-sm text-teal"><ArrowLeft size={16} aria-hidden />{order?.plan_review ? "Back to my generated plan" : "Back to my AI coach"}</Link>
    {!order && !error && <p role="status" className="mt-8">Loading your receipt…</p>}
    {error && <div className="mt-4"><ActionFeedback kind="error"><p>{serviceText(error)}</p><Button className="mt-3" variant="secondary" onClick={() => setRetry(r => r + 1)}>Refresh receipt</Button></ActionFeedback></div>}
    {order && <>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-4"><span className="font-mono text-[10px] text-white/45">ORDER {order.id.slice(0, 8).toUpperCase()}</span></div>
      <h1 className="mt-5 font-display text-3xl font-semibold sm:text-4xl">{titleFor(order)}</h1>
      <p className="mt-3 flex items-center gap-2 text-sm text-teal">{order.task?.status === "delivered" ? <CheckCircle2 size={16} aria-hidden /> : <Clock3 size={16} aria-hidden />}{order.task ? `${stateLabel(order.task.status)} · ${stateLabel(order.payment_state)}` : stateLabel(order.payment_state)}</p>
      
      <PurchaseJourney order={order} />
      <div className="mt-7 grid items-start gap-6 lg:grid-cols-[1.25fr_1fr]">
        <div className="space-y-5">{order.plan_review ? <PlanReviewSummary context={order.plan_review} /> : <ReviewReplay prefix={`/reviews/orders/${id}`} />}<p className="text-xs leading-6 text-white/50">{order.plan_review ? "Your generated plan is preserved. Your coach will review the shared copy alongside your restrictions and question." : "Your original video analysis is preserved. Your coaching request starts after payment confirmation."}</p></div>
        <div className="space-y-5">
          <section className="rounded-2xl border border-white/10 bg-[#0e1218] p-5 sm:p-6"><p className="font-mono text-[10px] uppercase tracking-wider text-teal">{paid ? "Receipt" : "Checkout summary"}</p><div className="mt-4 flex items-start justify-between gap-3"><h2 className="text-xl font-semibold">{order.package.name}</h2><span className="shrink-0 text-xl font-semibold">{usd(order.amount_cents)}</span></div><p className="mt-1 text-[11px] text-white/45">USD · one-time payment · {order.mode === "sandbox" ? "PayPal" : "practice checkout"}</p>
            <ul className="mt-5 space-y-2 text-xs leading-6 text-white/75">{order.package.deliverables.map(d => <li key={d}>✓ {serviceText(d)}</li>)}</ul><div className="mt-5 border-t border-white/10 pt-4"><p className="text-xs text-white/50">Your question</p><p className="mt-2 whitespace-pre-wrap text-sm leading-7">{order.question}</p></div>
            <p className="mt-4 text-xs leading-6 text-white/55">{order.plan_review ? "Sharing approved for your generated plan, saved restrictions, training preferences and coaching question." : <>Sharing approved for {order.sharing.recording_ids.length} selected clip{order.sharing.recording_ids.length > 1 ? "s" : ""}, saved evidence and this question. No other recordings are shared.</>}</p>
            {notice && !paid && <p className="mt-4 rounded-lg bg-teal/5 p-3 text-xs leading-6 text-teal" role="status">{serviceText(notice)}</p>}
            {order.payment_state === "capture_pending" && <div role="status" className="mt-5 rounded-xl border border-amber/30 bg-amber/5 p-4 text-sm leading-6 text-amber"><p className="font-semibold">Payment submitted · awaiting PayPal confirmation</p><p className="mt-2">PayPal is still processing or reviewing this payment. Your coach request will begin once payment is confirmed. Please refresh the status later; you do not need to pay again.</p></div>}
            {order.last_error && <p className="mt-4 text-xs leading-6 text-amber">{serviceText(order.last_error)}</p>}
            {order.mode === "simulated" && <p role="status" className="mt-4 text-xs leading-6 text-white/55">Practice checkout: no money is charged and no appointment is reserved.</p>}
            {order.mode === "sandbox" && paid && <p role="status" className="mt-4 rounded-xl border border-teal/30 p-4 text-sm text-teal">{order.payment_state === "paid" ? "Payment confirmed · your receipt is saved below." : stateLabel(order.payment_state)}</p>}
            {canCheckout && <div className="mt-5 space-y-3">
              {order.mode === "sandbox" ? <>
                {agentic && order.payment_state !== "capture_pending" && <PayPalSdkCheckout order={order} onUpdated={setOrder} onError={onSdkError} />}
                {!agentic && order.approval_url && order.payment_state !== "capture_pending" && <a className="flex min-h-12 items-center justify-center rounded-full bg-[#ffc439] px-5 text-sm font-semibold text-[#003087] hover:bg-[#ffd15f]" href={order.approval_url}>Approve on PayPal</a>}
                <Button className="w-full" disabled={busy || order.payment_state === "capture_pending"} loading={busy} onClick={() => action("capture")}>Confirm payment</Button>
                <p className="text-[11px] leading-5 text-white/55">Approve in PayPal, then confirm payment here if your receipt has not updated.</p>
              </> : <div className="rounded-xl border border-amber/25 p-4"><p className="mb-3 text-xs leading-6 text-amber">Practice checkout does not send a payment. Use it to explore your receipt and coaching request.</p><Button className="w-full" disabled={busy} onClick={() => action("simulate", { result: "completed" })}>Complete practice checkout</Button><div className="mt-2 flex flex-wrap gap-2"><Button variant="ghost" disabled={busy} onClick={() => action("simulate", { result: "pending" })}>Preview pending payment</Button><Button variant="ghost" disabled={busy} onClick={() => action("simulate", { result: "failed" })}>Preview failed payment</Button></div></div>}
              <Button className="w-full" variant="ghost" disabled={busy || order.payment_state === "capture_pending"} onClick={() => action("cancel")}>Cancel checkout</Button>
            </div>}
            <Button className="mt-4 w-full" variant="secondary" loading={busy} disabled={busy} onClick={() => action("reconcile")}>{order.mode === "sandbox" ? "Refresh payment status" : "Refresh payment status"}</Button>
            {order.provider_order_id && <details className="mt-4 text-xs text-white/50"><summary className="min-h-11 cursor-pointer py-3">Payment details</summary><ModeBadge mode={order.mode} /><p className="break-all font-mono text-[10px] leading-5">Order: {order.provider_order_id}<br />{order.capture_id && `Reference: ${order.capture_id}`}</p></details>}
          </section>
          {order.package.kind === "live_calls" && <CallSchedule order={order} onChanged={setOrder} />}
          <section className={`rounded-2xl border p-5 sm:p-6 ${order.task?.status === "delivered" ? "border-teal/40 bg-teal/5" : "border-white/10"}`}>
            <p className="font-mono text-[10px] uppercase tracking-wider text-teal">{agentic ? (order.package.kind === "ai_report" ? "AI technique report" : "Fulfillment status") : "Coach notes"}</p>
            {order.task?.delivered_text ? <>
              <p className="mt-3 text-xs text-white/60">{order.package.kind === "ai_report" ? "Automated report from saved analysis" : `Reviewed and approved by ${order.task.author}`} · {order.task.delivered_at && new Date(order.task.delivered_at).toLocaleDateString()}</p>
              <p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-white/90">{order.task.delivered_text}</p>
            </> : <>
              <h2 className="mt-3 text-xl font-semibold">
                {order.payment_state === "refunded" ? "Fulfillment canceled after refund"
                  : paid ? (serviceText(order.fulfillment?.delivery_label) || "Your request is queued.")
                    : "Fulfillment starts after verified payment."}
              </h2>
              <p className="mt-3 text-sm leading-7 text-white/60">
                {order.payment_state === "refund_pending" ? "Delivery is paused until the refund outcome is confirmed."
                  : paid ? (agentic
                    ? (order.package.kind === "live_calls"
                      ? (order.plan_review ? "Your shared plan and coach preferences are queued for review. The preferred time above is awaiting coach confirmation." : "Your session request is awaiting coach confirmation. You can request a preferred time above.")
                      : "Your review request is in the coach inbox. Approved feedback will appear here.")
                    : "Your coach can share notes from your calls here. Use your schedule above for confirmed times and video links.")
                    : "Your review or session request becomes available after payment confirmation."}
              </p>
              {order.task?.assessment && <p className="mt-3 text-xs leading-6 text-white/55">{serviceText(order.task.assessment)}</p>}
              <Button className="mt-4" variant="secondary" onClick={() => setRetry(r => r + 1)}>Check fulfillment status</Button>
            </>}
          </section>
          {order.shared_context && <SavedSuggestion context={order.shared_context} frozen />}
          {order.followup_available && supportOfferAppropriate(order.question) && order.sharing.recording_ids[0] && <section className="rounded-2xl border border-white/10 p-5"><h2 className="text-sm font-medium">More support, when you want it.</h2><p className="mt-3 text-xs leading-6 text-white/55">After your call or notes, you can review another individual session or a month of coaching. Each needs a separate purchase and fresh sharing consent.</p><div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">{[["additional-session", "Review another session"], ["month-coaching", "Explore a month"]].map(([service, label]) => <Link key={service} className="inline-flex min-h-11 items-center text-xs text-teal" href={`/reviews?connect=1&recording=${encodeURIComponent(order.sharing.recording_ids[0])}&followup=${encodeURIComponent(order.id)}&service=${service}`}>{label} →</Link>)}</div></section>}
          <details className="rounded-2xl border border-white/10 p-5"><summary className="cursor-pointer text-sm font-medium">Payment status history</summary><ol className="mt-4 space-y-4 border-l border-white/15 pl-4">{order.history.map((h, i) => <li key={i}><p className="text-xs font-medium text-teal">{stateLabel(h.state)}</p><p className="mt-1 text-xs leading-6 text-white/65">{serviceText(h.detail)}</p><p className="mt-1 text-[10px] text-white/40">{new Date(h.at).toLocaleString()}</p></li>)}</ol></details>
        </div>
      </div>
    </>}
  </AppShell>;
}
