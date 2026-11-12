"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { commerceRequest } from "@/lib/commerce";
import { buttonClass } from "@/lib/buttonStyles";

type Guide = { plan_id: string | null; recording_id: string | null; simulated: boolean; notice: string };
type Status = { available: boolean; active: boolean; seeded: boolean; can_return: boolean };
export default function DemoPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    api.demoStatus().then(async s => {
      if (!alive) return;
      setStatus(s);
      if (s.active) { const g = await commerceRequest<Guide>("/api/payments/demo-guide"); if (alive) setGuide(g); }
    }).catch(() => { if (alive) setError("Could not load the sample experience. Please try again."); });
    return () => { alive = false; };
  }, []);
  async function openDemo() {
    setBusy(true); setError("");
    try { await api.enterDemo(); window.location.assign("/demo"); } // eslint-disable-line @next/next/no-location-assign-relative-destination
    catch (e) { setError(e instanceof Error ? e.message : "Could not open the sample account."); setBusy(false); }
  }
  return <AppShell>
    <p className="text-xs uppercase tracking-wider text-teal">GhostRep · explore the experience</p>
    <h1 className="mt-3 max-w-2xl text-3xl font-semibold sm:text-4xl">From AI feedback to a coaching request you control.</h1>
    <p className="mt-4 max-w-2xl text-sm leading-7 text-white/70">Explore a sample training journal, review movement feedback, choose expert support, and follow your coaching request from checkout to delivery.</p>
    <p className="mt-4 rounded-xl border border-amber/25 p-4 text-xs leading-6 text-amber">Example workspace · sample recordings, example payments and coaching. Appointments shown here are not live reservations.</p>
    {error && <p role="alert" className="mt-4 text-sm text-amber">{error}</p>}
    {!status && !error && <p role="status" className="mt-5">Loading your sample experience…</p>}
    {status && !status.available && <p className="mt-5 text-sm leading-7">The sample experience is currently unavailable. You can build a plan with your own preferences below.</p>}
    {status?.available && !status.seeded && <p className="mt-5 text-sm leading-7">Run <code>make judge-setup</code>, then start the judge backend and frontend. Open this page on port 3110.</p>}
    {status?.available && status.seeded && !status.active && <Button className="mt-5" disabled={busy} loading={busy} onClick={openDemo}>Explore the example workspace</Button>}
    {guide && <div className="mt-7 grid gap-4 sm:grid-cols-2">
      {guide.plan_id && <section className="rounded-2xl border border-white/15 p-5"><p className="text-xs text-teal">01 · Plan review</p><h2 className="mt-3 text-xl font-semibold">Cross-check a training plan</h2><p className="mt-3 text-sm leading-7 text-white/65">Review a saved sample session, choose coach preferences, consent to the exact shared context, and try practice checkout at the fixed price.</p><Link className={buttonClass("primary", "mt-4")} href={`/reviews?plan=${encodeURIComponent(guide.plan_id)}`}>Try the plan review flow</Link></section>}
      {guide.recording_id && <section className="rounded-2xl border border-white/15 p-5"><p className="text-xs text-teal">02 · Movement evidence</p><h2 className="mt-3 text-xl font-semibold">Ask about a saved squat set</h2><p className="mt-3 text-sm leading-7 text-white/65">Replay a sample rep, ask about the movement feedback, and compare optional coaching services within your budget.</p><Link className={buttonClass("secondary", "mt-4")} href={`/reviews?recording=${encodeURIComponent(guide.recording_id)}`}>Explore movement & AI coach</Link></section>}
      <section className="rounded-2xl border border-white/15 p-5"><p className="text-xs text-teal">03 · Delivery</p><h2 className="mt-3 text-xl font-semibold">See the coach side</h2><p className="mt-3 text-sm leading-7 text-white/65">After practice checkout, explore the sample coach workspace to confirm a time and share feedback. Return to the training receipt to see the result.</p><Link className={buttonClass("secondary", "mt-4")} href="/coach">Open coach workspace</Link></section>
      <section className="rounded-2xl border border-white/15 p-5"><p className="text-xs text-teal">04 · Receipts & recovery</p><h2 className="mt-3 text-xl font-semibold">Follow every purchase</h2><p className="mt-3 text-sm leading-7 text-white/65">Review payment status, confirmation, delivery and refunds. Receipts remain available when you leave and return.</p><Link className={buttonClass("secondary", "mt-4")} href="/reviews">View purchases & receipts</Link></section>
    </div>}
    <section className="mt-8 border-t border-white/15 pt-5"><h2 className="text-lg font-semibold">Where PayPal fits</h2><p className="mt-3 max-w-3xl text-sm leading-7 text-white/70">Review the fixed price and approve your purchase through PayPal. Your coaching request starts after payment confirmation. Follow appointment confirmation, feedback and any refunds on the same receipt.</p><Link href="/onboarding" className="mt-3 inline-flex min-h-11 items-center text-sm text-teal">Build a plan with your own preferences →</Link></section>
  </AppShell>;
}
