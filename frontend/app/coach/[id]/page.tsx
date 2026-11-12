"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { ModeBadge } from "@/components/reviews/ReviewPrimitives";
import { CallSchedule } from "@/components/reviews/CallSchedule";
import { ReviewReplay } from "@/components/reviews/ReviewReplay";
import { PlanReviewSummary } from "@/components/reviews/PlanReviewSummary";
import { SavedSuggestion } from "@/components/reviews/SavedSuggestion";
import { commerceRequest, fieldClass, stateLabel, type ReviewOrder } from "@/lib/commerce";

export default function CoachTaskPage() {
  const { id } = useParams<{ id: string }>();
  const [order, setOrder] = useState<ReviewOrder | null>(null);
  const [draft, setDraft] = useState("");
  const [assessment, setAssessment] = useState("");
  const [comparison, setComparison] = useState("");
  const [nextSteps, setNextSteps] = useState("");
  const [approved, setApproved] = useState(false);
  const [ai, setAi] = useState(false);
  const [refundConfirm, setRefundConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  function apply(o: ReviewOrder) { setOrder(o); setDraft(o.task?.status === "delivered" ? o.task.delivered_text || "" : o.task?.draft || ""); setAssessment(o.task?.assessment || ""); setComparison(o.task?.ai_comparison || ""); setNextSteps(o.task?.next_steps || ""); setApproved(false); }
  useEffect(() => { let alive = true; commerceRequest<ReviewOrder>(`/coach/tasks/${id}`).then(o => { if (alive) apply(o); }).catch(e => { if (alive) setError(e.message); }); return () => { alive = false; }; }, [id]);
  async function action(path: string, body: unknown = {}, method?: string) {
    setBusy(true); setError(""); setNotice("");
    try { apply(await commerceRequest<ReviewOrder>(`/coach/tasks/${id}/${path}`, body, method)); setNotice(path === "deliver" ? "Your instructor notes were delivered to the athlete." : path === "draft" ? "Draft saved. Review this version before approving delivery." : "Task updated."); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not update this review."); }
    finally { setBusy(false); }
  }
  const editable = order?.payment_state === "paid" && !["delivered", "canceled"].includes(order?.task?.status || "");
  const dirty = draft !== (order?.task?.draft || "") || assessment !== (order?.task?.assessment || "") || comparison !== (order?.task?.ai_comparison || "") || nextSteps !== (order?.task?.next_steps || "");
  const hasDraft = Boolean(draft.trim() || assessment.trim());
  return <AppShell><Link href="/coach" className="inline-flex min-h-11 items-center text-sm text-teal">← Coach inbox</Link>
    {error && <div className="mt-4"><ActionFeedback kind="error">{error} {!order && <Link href="/coach" className="ml-2 underline">Sign in to the workspace</Link>}</ActionFeedback></div>}
    {!order && !error && <p role="status" className="mt-8">Loading the shared task…</p>}
    {order && <><div className="mt-5 flex flex-wrap items-center justify-between gap-3"><ModeBadge mode={order.mode} /><span className="text-xs text-teal">{stateLabel(order.payment_state)} / {stateLabel(order.task?.status || "queued")}</span></div><h1 className="mt-5 font-display text-3xl font-semibold">{order.package.name}</h1><p className="mt-4 max-w-3xl whitespace-pre-wrap text-lg leading-8 text-white/85">“{order.question}”</p><p className="mt-3 text-xs leading-6 text-white/50">Purchased: {order.package.deliverables.join(" · ")}. {order.plan_review ? "Sharing is limited to this task’s saved plan, restrictions and preferences." : "Sharing is limited to this paid task’s selected clips."}</p>
      {order.plan_review && <PlanReviewSummary context={order.plan_review} />}
      {order.shared_context && <SavedSuggestion context={order.shared_context} frozen />}
      <div className="mt-6"><CallSchedule order={order} coach onChanged={o => setOrder(o)} /></div>
      <div className="mt-7 grid items-start gap-6 lg:grid-cols-2"><div>{order.payment_state === "paid" ? order.plan_review ? <p className="text-sm text-white/65">Review the shared plan and restrictions above. No video was shared.</p> : <ReviewReplay prefix={`/coach/tasks/${id}`} /> : <p className="rounded-2xl border border-amber/25 p-6 text-sm leading-7 text-amber">Clip sharing is paused or ended for this payment. Reconcile a pending refund before continuing delivery.</p>}</div>
        <section className="rounded-2xl border border-white/10 bg-[#0e1218] p-5 sm:p-6"><p className="font-mono text-[10px] uppercase tracking-wider text-teal">Coach response</p><h2 className="mt-3 text-xl font-semibold">{order.task?.status === "delivered" ? "Delivered with your approval" : "Evidence first. Your judgment next."}</h2>
          {editable && <><p className="mt-3 text-xs leading-6 text-white/60">Generate a starting point, then edit it to answer the question. Drafts are private. The athlete sees only your approved delivery.</p><label className="mt-5 flex items-start gap-3"><input type="checkbox" checked={ai} disabled={!order.sharing.ai_consented_at || busy} onChange={e => setAi(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-teal" /><span className="text-xs leading-6 text-white/65">Request Muse Spark fact selection using bounded saved evidence. This may use the operator’s AI credits. {order.sharing.ai_consented_at ? "The athlete has consented to AI processing." : "Unavailable: athlete AI consent was not given. A local evidence draft is available."}</span></label><Button className="mt-4 w-full" variant="secondary" disabled={busy || dirty} onClick={() => action("draft/generate", { ai_consent: ai })}>{order.plan_review ? "Create plan review outline" : ai ? "Generate AI-assisted draft" : "Create local evidence draft"}</Button>{dirty && <p className="mt-2 text-xs text-amber">Save your edits before generating another draft.</p>}</>}
          <p className="mt-5 text-[11px] text-white/50">{order.task?.draft_source || "Human draft"} · revision {order.task?.revision || 0}</p>
          {editable && <div className="mt-5 space-y-5"><p className="text-xs leading-6 text-white/65">Your assessment is independent of the AI. Explain what you observed, where you agree or disagree, and how you would tailor the guidance.</p><label className="block text-sm">Your independent assessment<textarea rows={4} maxLength={3000} className={fieldClass} value={assessment} disabled={busy} onChange={e => { setAssessment(e.target.value); setApproved(false); }} placeholder="Describe what you observed in the movement. Cite a clip or rep when helpful." /></label><label className="block text-sm">Your view of the saved suggestion<textarea rows={4} maxLength={3000} className={fieldClass} value={comparison} disabled={busy} onChange={e => { setComparison(e.target.value); setApproved(false); }} placeholder="Explain what you agree with, would correct, or cannot assess. You do not need to approve the AI suggestion." /></label><label className="block text-sm">Tailored next steps<textarea rows={3} maxLength={3000} className={fieldClass} value={nextSteps} disabled={busy} onChange={e => { setNextSteps(e.target.value); setApproved(false); }} placeholder="Give the athlete a practical focus adapted to their question and the available evidence." /></label></div>}
          <label className="mt-5 block text-sm">{editable ? "Additional notes or evidence draft (optional)" : "Saved instructor response"}<textarea rows={editable ? 6 : 15} className={fieldClass} value={draft} maxLength={10000} disabled={!editable || busy} placeholder="Optional supporting observations and rep references." onChange={e => { setDraft(e.target.value); setApproved(false); }} /></label>
          {editable && <><Button className="mt-4 w-full" variant="secondary" disabled={busy || !hasDraft || !dirty} onClick={() => action("draft", { text: draft, assessment, ai_comparison: comparison, next_steps: nextSteps, revision: order.task?.revision || 0 }, "PUT")}>Save draft{dirty ? " · unsaved changes" : ""}</Button><label className="mt-6 flex items-start gap-3 rounded-xl border border-teal/25 bg-teal/5 p-4"><input type="checkbox" checked={approved} disabled={busy || dirty || !hasDraft} onChange={e => setApproved(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-teal" /><span className="text-xs leading-6 text-white/80">{order.plan_review ? "I reviewed the shared plan, restrictions and this saved assessment, and approve it for delivery under my coach identity." : "I watched the selected evidence, reviewed this saved draft, and approve it for delivery under my coach identity."}</span></label><Button className="mt-4 w-full" disabled={busy || !approved || dirty} loading={busy} onClick={() => action("deliver", { reviewed_and_approved: approved, revision: order.task?.revision || 0 })}>Approve & deliver feedback</Button></>}
          {order.task?.author && <p className="mt-4 text-xs text-teal">Instructor: {order.task.author} · {order.task.delivered_at && new Date(order.task.delivered_at).toLocaleString()}</p>}
          {notice && <p role="status" className="mt-4 text-xs leading-6 text-teal">{notice}</p>}
          <details className="mt-6 border-t border-white/10 pt-5"><summary className="cursor-pointer text-xs text-white/65">Payment management · coach authorized</summary><p className="mt-3 text-xs leading-6 text-white/55">A full refund pauses delivery and ends coach clip access once confirmed. Delivered feedback and receipts remain available to the athlete.</p><Button className="mt-3 w-full" variant="secondary" disabled={busy} onClick={() => action("reconcile")}>Refresh payment status</Button>{order.refund && <p className="mt-3 text-xs text-amber">Refund: {order.refund.state} {order.refund.last_error}</p>}{order.payment_state !== "refunded" && <>{refundConfirm ? <div className="mt-4 rounded-xl border border-amber/30 p-4"><p className="text-xs leading-6 text-amber">Confirm a full {order.mode === "simulated" ? "practice" : "test-payment"} refund of this purchase?</p><div className="mt-3 flex gap-2"><Button variant="amber" disabled={busy} onClick={() => { void action("refund"); setRefundConfirm(false); }}>Confirm full refund</Button><Button variant="ghost" onClick={() => setRefundConfirm(false)}>Keep order</Button></div></div> : <Button className="mt-3 w-full" variant="ghost" disabled={busy || !["paid", "refund_pending"].includes(order.payment_state)} onClick={() => setRefundConfirm(true)}>Request full refund</Button>}</>}</details>
        </section>
      </div></>}
  </AppShell>;
}
