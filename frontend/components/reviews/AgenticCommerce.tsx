"use client";

import { serviceText } from "@/lib/commerceCopy";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, LockKeyhole, Sparkles } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { ModeBadge, PackageCard } from "./ReviewPrimitives";
import { api } from "@/lib/api";
import { questionForHuman, supportOfferAppropriate } from "@/lib/coachChat";
import {
  commerceRequest, fieldClass, parseBudget, usd,
  type AgenticRecommendResponse, type ReviewOrder, type ReviewPackage,
} from "@/lib/commerce";
import type { RecordedSet } from "@/lib/types";

export function AgenticCommerce({ recordingId }: { recordingId: string }) {
  const router = useRouter();
  const [recording, setRecording] = useState<RecordedSet | null>(null);
  const [catalog, setCatalog] = useState<ReviewPackage[]>([]);
  const [question, setQuestion] = useState("");
  const [budget, setBudget] = useState("");
  const [sharing, setSharing] = useState(false);
  const [approved, setApproved] = useState(false);
  const [packageId, setPackageId] = useState<string | null>(null);
  const [result, setResult] = useState<AgenticRecommendResponse | null>(null);
  const [checkoutKey, setCheckoutKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.getRecording(recordingId),
      commerceRequest<{ packages: ReviewPackage[] }>("/api/payments/catalog"),
      api.coachConversation(recordingId).catch(() => ({ turns: [] })),
    ]).then(([rec, cat, conversation]) => {
      if (!alive) return;
      setRecording(rec);
      setCatalog(cat.packages);
      setError("");
      setQuestion(current => current || questionForHuman(conversation.turns.at(-1), rec.id) || "I want coaching focused on the form issues in this squat set.");
      setPackageId(cat.packages[0]?.id || null);
    }).catch(() => { if (alive) setError("This recording couldn’t load for coaching recommendations. Return to My coach and try again."); });
    return () => { alive = false; };
  }, [recordingId, retry]);

  const mode = recording?.is_sample || recording?.entry_source === "demo" ? "simulated" : "sandbox";
  const chosen = (result?.catalog || catalog).find(p => p.id === packageId) || catalog.find(p => p.id === packageId);
  const recommendation = result?.recommendation;

  async function requestRecommendation() {
    if (!supportOfferAppropriate(question)) {
      setError("Safety or pain-related questions are not used to recommend a purchase. Keep using free feedback.");
      return;
    }
    setBusy(true); setError(""); setApproved(false);
    try {
      const budgetCents = parseBudget(budget);
      const response = await commerceRequest<AgenticRecommendResponse>("/api/payments/recommendations", {
        question, recording_ids: [recordingId], share_with_coach: sharing, ai_consent: false, mode, budget_cents: budgetCents,
      });
      setResult(response);
      setCheckoutKey(crypto.randomUUID());
      setPackageId(response.recommendation.package_id || response.catalog[0]?.id || null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Recommendation failed. No charge was made.");
    } finally {
      setBusy(false);
    }
  }

  async function startCheckout() {
    if (!result || !packageId || !approved) return;
    setBusy(true); setError("");
    try {
      const order = await commerceRequest<ReviewOrder>("/api/payments/orders", {
        intake_id: result.id, package_id: packageId, checkout_key: checkoutKey || crypto.randomUUID(), approved: true,
      });
      router.push(`/reviews/${order.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Checkout could not start. No payment was captured.");
    } finally {
      setBusy(false);
    }
  }

  const back = `/reviews?recording=${encodeURIComponent(recordingId)}`;
  return <AppShell>
    <Link href={back} className="inline-flex min-h-11 items-center gap-2 text-sm text-white/65 hover:text-teal"><ArrowLeft size={15} aria-hidden />Back to my AI coach</Link>
    <header className="mt-5 max-w-2xl">
      <p className="font-mono text-[10px] uppercase tracking-[.2em] text-teal">Coaching for your next session</p>
      <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">Coaching matched to this set.</h1>
      <p className="mt-4 text-sm leading-7 text-white/60">
        Explore support for your saved squat set. Compare services and prices, review what you’ll share, then pay securely with PayPal when you’re ready.
      </p>
    </header>
    {error && <div role="alert" className="mt-5 rounded-xl border border-amber/25 p-4 text-sm leading-7 text-amber">{error}<Button variant="secondary" className="ml-3" onClick={() => setRetry(r => r + 1)}>Retry</Button></div>}
    {!recording && !error && <p className="mt-8 text-sm text-white/50" role="status">Loading your set…</p>}
    {recording && <>
      <details className="mt-5 text-xs text-white/50"><summary className="min-h-11 cursor-pointer py-3">Payment environment</summary><ModeBadge mode={mode} /></details>
      <div className="mt-6 grid items-start gap-7 lg:grid-cols-[1.05fr_1fr]">
        <section className="space-y-4">
          <h2 className="text-sm font-medium text-white/70">Choose your support</h2>
          <div className="grid gap-4">{catalog.map(p => (
            <PackageCard key={p.id} item={p} selected={p.id === packageId} onSelect={busy ? undefined : () => { setPackageId(p.id); setApproved(false); }} />
          ))}</div>
        </section>
        <section className="rounded-2xl border border-white/10 bg-[#0e1218] p-5 sm:p-6" aria-label="Recommendation and checkout">
          <div className="flex items-start gap-3"><Sparkles className="mt-1 shrink-0 text-teal" size={18} aria-hidden /><div>
            <h2 className="text-lg font-semibold">Recommendation from your workout</h2>
            <p className="mt-2 text-xs leading-6 text-white/55">{recording.exercise_name || "Barbell squat"}{recording.set_index ? ` · Set ${recording.set_index}` : ""}</p>
          </div></div>
          <label className="mt-5 block text-sm" htmlFor="agentic-question">What should coaching focus on?
            <textarea id="agentic-question" rows={3} maxLength={1200} className={fieldClass} value={question} disabled={busy} onChange={e => { setQuestion(e.target.value); setResult(null); setApproved(false); }} />
          </label>
          <label className="mt-4 block text-sm" htmlFor="agentic-budget">Optional budget (USD)
            <input id="agentic-budget" className={fieldClass} value={budget} disabled={busy} placeholder="e.g. 20" onChange={e => { setBudget(e.target.value); setResult(null); setApproved(false); }} />
          </label>
          <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 p-4">
            <input type="checkbox" checked={sharing} disabled={busy} onChange={e => { setSharing(e.target.checked); setResult(null); }} className="mt-1 h-4 w-4 shrink-0 accent-teal" />
            <span className="text-xs leading-6 text-white/75">I consent to share this selected clip, saved movement evidence, and the question above for a coaching recommendation. Checkout still requires a separate approval.</span>
          </label>
          <Button className="mt-5 w-full" disabled={busy || !sharing || question.trim().length < 10} loading={busy} loadingLabel="Analyzing…" onClick={requestRecommendation}>
            Analyze set & recommend<ArrowRight size={16} aria-hidden />
          </Button>

          {recommendation && <div className="mt-6 space-y-4 border-t border-white/10 pt-5">
            <p className="font-mono text-[10px] uppercase tracking-wider text-teal">{recommendation.source === "deterministic_movement" ? "Based on your saved movement analysis" : serviceText(recommendation.source_label)}</p>
            <p className="text-sm leading-7 text-white/85">{serviceText(recommendation.explanation)}</p>
            {recommendation.analysis && <p className="text-xs leading-6 text-white/55">Signals: {recommendation.analysis.summary}</p>}
            {recommendation.analysis?.findings && recommendation.analysis.findings.length > 0 && <section aria-label="Evidence behind this recommendation" className="rounded-xl border border-teal/25 p-4"><h3 className="text-sm font-medium text-teal">{recommendation.outcome === "recommend" ? "Why this recommendation?" : "Saved movement evidence"}</h3><ul className="mt-3 space-y-3">{recommendation.analysis.findings.map((fact,i) => <li key={i} className="text-xs leading-6 text-white/75"><p>{fact.text}</p><Link href={`/analysis/${encodeURIComponent(fact.recording_id)}?rep=${fact.rep_id}${fact.seconds != null ? `&t=${fact.seconds}` : ""}`} className="inline-flex min-h-11 items-center text-teal">Replay supporting rep {fact.rep_id} →</Link></li>)}</ul><p className="mt-2 text-xs leading-6 text-white/50">Comparison with your own observed reference, not a technique or safety grade. You can keep using free feedback.</p></section>}
            {recommendation.comparison && recommendation.comparison.length > 0 && (
              <ul className="space-y-2 text-xs leading-6 text-white/65">
                {recommendation.comparison.map(item => (
                  <li key={item.id} className="rounded-lg border border-white/10 px-3 py-2">
                    <span className="font-medium text-white/85">{item.name}</span> · {usd(item.price_cents)} · {serviceText(item.expertise)}
                  </li>
                ))}
              </ul>
            )}
            {recommendation.outcome === "recommend" && chosen && <>
              <div className="flex items-start justify-between gap-3 rounded-xl border border-teal/25 bg-teal/5 p-4">
                <div>
                  <p className="text-sm font-medium">{chosen.name}</p>
                  <p className="mt-1 text-xs text-white/55">{serviceText(chosen.delivery_label || chosen.description)}</p>
                </div>
                <p className="text-xl font-semibold">{usd(chosen.price_cents)}</p>
              </div>
              {(recommendation.alternatives || []).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {recommendation.alternatives!.map(alt => (
                    <button key={alt.id} type="button" disabled={busy} onClick={() => { setPackageId(alt.id); setApproved(false); }}
                      className={`min-h-10 rounded-full border px-3 text-xs ${packageId === alt.id ? "border-teal text-teal" : "border-white/15 text-white/65"}`}>
                      Choose {alt.name} ({usd(alt.price_cents)})
                    </button>
                  ))}
                  <button type="button" disabled={busy} onClick={() => { setApproved(false); setPackageId(null); }}
                    className="min-h-10 rounded-full border border-white/15 px-3 text-xs text-white/55">Reject recommendation</button>
                </div>
              )}
              <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 p-4">
                <input type="checkbox" checked={approved} disabled={busy || !packageId} onChange={e => setApproved(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-teal" />
                <span className="text-xs leading-6 text-white/75">I approve starting {mode === "simulated" ? "practice checkout" : "PayPal checkout"} for {chosen ? `${chosen.name} at ${usd(chosen.price_cents)}` : "the selected service"}. Purchases remain locked until the selected payment flow is confirmed.</span>
              </label>
              <Button className="w-full" disabled={busy || !approved || !packageId} loading={busy} loadingLabel="Preparing checkout…" onClick={startCheckout}>
                {mode === "simulated" ? "Continue to practice checkout" : "Continue to PayPal"}
              </Button>
            </>}
            {recommendation.outcome !== "recommend" && <p className="text-xs leading-6 text-white/55">{serviceText(recommendation.limits)}</p>}
          </div>}
          <p className="mt-4 flex items-start gap-2 text-[11px] leading-6 text-white/45"><LockKeyhole size={13} className="mt-1 shrink-0" aria-hidden />One-time prices. You approve the service and total before payment.</p>
        </section>
      </div>
    </>}
  </AppShell>;
}
