"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ArrowRight, Play, Video } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { RecordingCoach } from "@/components/reviews/RecordingCoach";
import { HumanCoaching } from "@/components/reviews/HumanCoaching";
import { PlanCoachCheckout } from "@/components/reviews/PlanCoachCheckout";
import { AgenticCommerce } from "@/components/reviews/AgenticCommerce";
import { OrderLink } from "@/components/reviews/ReviewPrimitives";
import { Button } from "@/components/ui/button";
import { buttonClass } from "@/lib/buttonStyles";
import { commerceRequest, type ReviewOrder, type ReviewRecording } from "@/lib/commerce";

export default function ReviewsPage() {
  return <Suspense fallback={<AppShell><p role="status" className="text-sm text-white/50">Opening My coach…</p></AppShell>}><CoachRoute /></Suspense>;
}

function CoachRoute() {
  const query = useSearchParams();
  const plan = query.get("plan");
  if (plan) return <PlanCoachCheckout key={plan} planId={plan} />;
  const recording = query.get("recording");
  if (recording) {
    if (query.get("agentic") === "1") return <AgenticCommerce key={`agentic-${recording}`} recordingId={recording} />;
    if (query.get("connect") === "1") {
      return <HumanCoaching key={`human-${recording}-${query.get("followup") || ""}`} recordingId={recording} previousOrderId={query.get("followup") || undefined} initialPackageId={query.get("service") || undefined} />;
    }
    return <RecordingCoach key={recording} recordingId={recording} />;
  }
  return <CoachHub />;
}

function CoachHub() {
  const [recordings, setRecordings] = useState<ReviewRecording[]>([]);
  const [orders, setOrders] = useState<ReviewOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    commerceRequest<ReviewRecording[]>("/reviews/recordings").then(async rows => {
      const receipts = await commerceRequest<ReviewOrder[]>("/reviews/orders");
      if (alive) { setRecordings(rows); setOrders(receipts); setError(""); }
    }).catch(() => { if (alive) setError("Your sets couldn’t load. Check your connection and try again."); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [retry]);
  const own = recordings.filter(r => !r.synthetic);
  const samples = recordings.filter(r => r.synthetic);
  return <AppShell>
    <header className="mt-2 flex flex-wrap items-start justify-between gap-5 border-b border-white/10 pb-7"><div><p className="font-mono text-[10px] uppercase tracking-[.2em] text-teal">Your training companion</p><h1 className="mt-3 font-display text-3xl font-semibold sm:text-4xl">My coach</h1><p className="mt-3 max-w-lg text-sm leading-7 text-white/60">Replay a set, understand the feedback, and ask your next question.</p></div><Link href="/record" className={buttonClass("primary", "mt-2")}><Video size={16} aria-hidden />Record or upload<ArrowRight size={15} aria-hidden /></Link></header>
    {error && <div role="alert" className="mt-5 rounded-xl border border-amber/25 p-4 text-sm text-amber">{error}<Button variant="ghost" className="ml-3" onClick={() => setRetry(r => r + 1)}>Try again</Button></div>}
    {loading && <p role="status" className="mt-8 text-sm text-white/50">Loading your recent sets…</p>}
    {!loading && !error && <section className="mt-8"><h2 className="text-lg font-semibold">Recent sets</h2><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{own.length ? own.slice(0, 12).map(r => <SetCard key={r.id} recording={r} />) : <div className="col-span-full rounded-2xl border border-dashed border-white/15 bg-white/[0.015] p-7 sm:p-9"><Video size={25} className="text-teal" aria-hidden /><h3 className="mt-4 text-xl font-semibold">Start with your movement.</h3><p className="mt-3 max-w-lg text-sm leading-7 text-white/60">Save a squat clip to see feedback and ask your AI coach about the moments that matter. Live coaching is optional.</p><Link href="/record" className="mt-4 inline-flex min-h-11 items-center gap-2 text-sm text-teal">Record your first set<ArrowRight size={14} aria-hidden /></Link></div>}</div></section>}
    {orders.length > 0 && <section className="mt-9 border-t border-white/10 pt-6"><h2 className="text-lg font-semibold">Coaching purchases & receipts</h2><p className="mt-2 text-xs leading-6 text-white/50">Your coaching requests, appointments, feedback and payment history.</p><div className="mt-4 grid gap-3 sm:grid-cols-2">{orders.map(o => <OrderLink key={o.id} order={o} />)}</div></section>}
    {samples.length > 0 && <details className="mt-8 border-t border-white/10 pt-5"><summary className="cursor-pointer py-2 text-xs text-white/45">Sample recordings</summary><p className="mt-2 text-xs leading-6 text-white/50">These examples use generated movement evidence. They do not count as performed training.</p><div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{samples.map(r => <SetCard key={r.id} recording={r} />)}</div></details>}
  </AppShell>;
}

function SetCard({ recording: r }: { recording: ReviewRecording }) {
  return <Link href={`/reviews?recording=${encodeURIComponent(r.id)}`} className="group rounded-2xl border border-white/10 bg-[#0e1218] p-5 transition hover:border-teal/45"><div className="flex items-center justify-between gap-3"><span className="rounded-xl bg-teal/8 p-3 text-teal"><Play size={17} aria-hidden /></span><span className="text-[11px] text-white/45">{new Date(r.created_at).toLocaleDateString([], { month: "short", day: "numeric" })}</span></div><h3 className="mt-4 text-base font-semibold">Squat{r.set_index ? ` · Set ${r.set_index}` : " recording"}</h3><p className="mt-2 text-xs leading-6 text-white/55">{r.synthetic ? "Sample recording" : r.analysis_ready ? `${r.detected_reps} measured reps` : r.processing_status === "FAILED" ? "Analysis needs another try" : !["SAVED", "COMPLETED"].includes(r.processing_status) ? "Preparing your feedback" : "Saved video · no measured reps"}{!r.has_video && !r.synthetic ? " · video unavailable" : ""}</p><span className="mt-5 inline-flex items-center gap-2 text-xs text-teal">Open feedback & AI coach<ArrowRight size={14} aria-hidden /></span></Link>;
}
