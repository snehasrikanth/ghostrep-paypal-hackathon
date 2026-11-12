"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { commerceRequest, fieldClass, usd, type PlanReviewContext, type ReviewCatalog, type ReviewPackage, type ReviewOrder } from "@/lib/commerce";
import { ModeBadge } from "./ReviewPrimitives";
import { PlanReviewSummary } from "./PlanReviewSummary";

export function PlanCoachCheckout({ planId }: { planId: string }) {
  const router = useRouter();
  const [plan, setPlan] = useState<PlanReviewContext | null>(null);
  const [service, setService] = useState<ReviewPackage | null>(null);
  const [configured, setConfigured] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const [consent, setConsent] = useState(false), [approved, setApproved] = useState(false);
  const [gender, setGender] = useState("no_preference"), [nationality, setNationality] = useState("No preference");
  const [language, setLanguage] = useState("English"), [experience, setExperience] = useState("any"), [specialty, setSpecialty] = useState("general");
  const [suggestedTimes, setSuggestedTimes] = useState<{ label: string; value: string }[]>([]);
  const [time, setTime] = useState(""), [zone, setZone] = useState("UTC");
  const [question, setQuestion] = useState("Please cross-check my generated plan against my restrictions, training goals and experience. Explain any changes you recommend.");
  const [intake, setIntake] = useState<string | null>(null);
  const [key, setKey] = useState("");
  useEffect(() => {
    let alive = true;
    Promise.all([commerceRequest<PlanReviewContext>(`/api/payments/plan-reviews/${encodeURIComponent(planId)}`), commerceRequest<ReviewCatalog>("/api/payments/catalog")])
      .then(([saved, cat]) => { if (alive) { setZone(Intl.DateTimeFormat().resolvedOptions().timeZone);
        setSuggestedTimes([{ days: 1, hour: 18, label: "Tomorrow · 6 PM" }, { days: 2, hour: 12, label: "In 2 days · noon" }].map(slot => {
          const date = new Date(); date.setDate(date.getDate() + slot.days); date.setHours(slot.hour, 0, 0, 0);
          const local = new Date(date.getTime() - date.getTimezoneOffset()*60000).toISOString().slice(0,16);
          return { label: slot.label, value: local };
        })); setPlan(saved); setService(cat.packages.find(p => p.id === "personal-coaching-session") || null); setConfigured(cat.sandbox_configured); setError(""); } })
      .catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [planId, retry]);
  function changed() { setIntake(null); setApproved(false); setConsent(false); }
  async function checkout() {
    if (!plan || !service || !consent || !approved || busy) return;
    setBusy(true); setError("");
    try {
      let intakeId = intake;
      let checkoutKey = key;
      if (!intakeId) {
        const result = await commerceRequest<{ id: string }>("/api/payments/plan-reviews", { plan_id: planId, context_fingerprint: plan.fingerprint, question, share_with_coach: consent,
          preferences: { gender, nationality, language, experience, specialty, preferred_at: new Date(time).toISOString(), timezone: zone } });
        intakeId = result.id; checkoutKey = crypto.randomUUID(); setIntake(intakeId); setKey(checkoutKey);
      }
      const order = await commerceRequest<ReviewOrder>("/api/payments/orders", { intake_id: intakeId, package_id: service.id, checkout_key: checkoutKey, approved: true });
      router.push(`/reviews/${order.id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Checkout could not start. Please try again."); }
    finally { setBusy(false); }
  }
  return <AppShell>
    <Link href={`/workouts/${encodeURIComponent(planId)}`} className="inline-flex min-h-11 items-center text-sm text-teal">← Back to your generated plan</Link>
    <p className="mt-5 text-xs uppercase tracking-wider text-teal">Live coach · plan review</p>
    <h1 className="mt-3 text-3xl font-semibold">A second perspective on your plan.</h1>
    <p className="mt-3 max-w-2xl text-sm leading-7 text-white/70">Choose the coach preferences that help you feel comfortable. A coach can review your exercise selection, workload and restrictions with you in a 30-minute session.</p>
    {error && <div role="alert" className="mt-5 rounded-xl border border-amber/30 p-4 text-sm text-amber">{error}{!plan && <Button variant="ghost" onClick={() => setRetry(n => n+1)}>Retry</Button>}</div>}
    {!plan && !error && <p role="status" className="mt-6">Loading your plan…</p>}
    {plan && <div className="mt-6 grid items-start gap-6 lg:grid-cols-2"><PlanReviewSummary context={plan} />
      <form onSubmit={e => { e.preventDefault(); void checkout(); }} className="rounded-2xl border border-white/15 bg-card p-5">
        <h2 className="text-xl font-semibold">Your coach preferences</h2>
        <p className="mt-2 text-xs leading-6 text-white/60">Your preferences help with coach matching. We’ll confirm your coach and session time before your appointment.</p>
        <fieldset disabled={busy} className="mt-4 grid gap-4 sm:grid-cols-2" onChange={changed}>
          <label className="text-sm">Gender preference<select value={gender} onChange={e => setGender(e.target.value)} className={fieldClass}><option value="no_preference">No preference</option><option value="female">Female</option><option value="male">Male</option><option value="nonbinary">Nonbinary</option></select></label>
          <label className="text-sm">Nationality preference<input maxLength={80} required value={nationality} onChange={e => setNationality(e.target.value)} className={fieldClass} list="coach-nationalities" /><datalist id="coach-nationalities">{["No preference", "Indian", "American", "British", "Canadian", "Australian", "Other / discuss with me"].map(v => <option key={v} value={v} />)}</datalist></label>
          <label className="text-sm">Preferred language<input required maxLength={80} value={language} onChange={e => setLanguage(e.target.value)} className={fieldClass} list="coach-languages" /><datalist id="coach-languages">{["English", "Hindi", "Tamil", "Telugu", "Spanish", "French", "Mandarin", "Arabic"].map(v => <option key={v} value={v} />)}</datalist></label>
          <label className="text-sm">Coaching experience<select value={experience} onChange={e => setExperience(e.target.value)} className={fieldClass}><option value="any">No preference</option><option value="3_plus">3+ years</option><option value="5_plus">5+ years</option><option value="10_plus">10+ years</option></select></label>
          <label className="text-sm sm:col-span-2">Coaching focus<select value={specialty} onChange={e => setSpecialty(e.target.value)} className={fieldClass}><option value="general">Plan and exercise selection</option><option value="beginner">Beginner training</option><option value="strength">Strength and squat technique</option><option value="mobility">Mobility and movement</option><option value="adapted_training">Adapting training to restrictions</option></select></label>
          <label className="text-sm sm:col-span-2">Preferred session time<input type="datetime-local" required value={time} onChange={e => setTime(e.target.value)} className={fieldClass} /><span className="mt-2 block text-xs text-white/50">{zone} · at least one hour ahead, within 90 days. Availability requires confirmation.</span></label>
          <div className="sm:col-span-2"><p className="text-xs text-white/55">Quick preferred times · requests, not confirmed availability</p><div className="mt-2 flex flex-wrap gap-2">{suggestedTimes.map(slot => <button key={slot.value} type="button" aria-pressed={time === slot.value} onClick={() => { changed(); setTime(slot.value); }} className={`min-h-11 rounded-full border px-3 text-xs ${time === slot.value ? "border-teal text-teal" : "border-white/20 text-white/75"}`}>{slot.label}</button>)}</div></div>
          <label className="text-sm sm:col-span-2">What would you like verified?<textarea required rows={4} maxLength={1200} value={question} onChange={e => setQuestion(e.target.value)} className={fieldClass} /></label>
        </fieldset>
        <div className="mt-5 rounded-xl border border-teal/25 p-4"><p className="text-sm font-medium">{service?.name || "Personal Coaching Session"}<span className="float-right text-teal">{service ? usd(service.price_cents) : "Unavailable"}</span></p><p className="mt-2 text-xs leading-6 text-white/60">30 minutes · fixed one-time price · {plan.mode === "simulated" ? "practice checkout" : "PayPal"}</p></div>
        <details className="mt-3 text-xs text-white/50"><summary className="min-h-11 cursor-pointer py-3">Payment environment</summary><ModeBadge mode={plan.mode} /></details>
        <label className="mt-4 flex items-start gap-3 text-xs leading-6"><input type="checkbox" checked={consent} disabled={busy} onChange={e => { setConsent(e.target.checked); setApproved(false); }} className="mt-1 h-5 w-5 shrink-0 accent-teal" />I agree to share the plan, saved restrictions, training preferences, question and coach preferences shown here for this review.</label>
        <label className="mt-4 flex items-start gap-3 text-xs leading-6"><input type="checkbox" checked={approved} disabled={busy || !consent} onChange={e => setApproved(e.target.checked)} className="mt-1 h-5 w-5 shrink-0 accent-teal" />I approve {service ? usd(service.price_cents) : "the fixed price"} for this session request. Matching and availability are pending confirmation.</label>
        {!configured && plan.mode !== "simulated" && <p className="mt-3 text-xs leading-6 text-amber">Checkout is temporarily unavailable. Your plan and preferences are saved.</p>}
        <Button type="submit" className="mt-5 w-full" disabled={busy || !consent || !approved || !service || (!configured && plan.mode !== "simulated") || !time} loading={busy}>{plan.mode === "simulated" ? "Continue to practice checkout" : "Continue to PayPal"}</Button>
        <p className="mt-3 text-xs leading-6 text-white/50">Complete payment on the next screen. Your coach request is sent after payment confirmation, and your appointment time will be confirmed separately.</p>
      </form>
    </div>}
  </AppShell>;
}
