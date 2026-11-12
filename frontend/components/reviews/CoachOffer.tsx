"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Video, ArrowRight } from "lucide-react";
import { commerceRequest, usd, type ReviewPackage } from "@/lib/commerce";
import { buttonClass } from "@/lib/buttonStyles";

export function CoachOffer({ recordingId, planId, context = "set" }: { recordingId?: string; planId?: string; context?: "set" | "finding" | "plan" }) {
  const [catalog, setCatalog] = useState<ReviewPackage[]>([]);
  useEffect(() => {
    let alive = true;
    commerceRequest<{ packages: ReviewPackage[] }>("/api/payments/catalog")
      .then(data => { if (alive) setCatalog(data.packages); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  const href = context === "plan" ? (planId ? `/reviews?plan=${encodeURIComponent(planId)}` : "/program") : recordingId ? `/reviews?agentic=1&recording=${encodeURIComponent(recordingId)}` : "/reviews";
  return <section className="mt-4 rounded-2xl border border-teal/35 bg-teal/5 p-5" aria-label="Live coaching and payment options">
    <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-teal"><Video size={16} aria-hidden />Live coach support</p>
    <h3 className="mt-2 text-lg font-semibold">{context === "plan" ? "Want to cross-check your plan with a live coach?" : context === "finding" ? "Get a live coach’s perspective on this movement." : "Want a second opinion from a live coach?"}</h3>
    <p className="mt-2 text-sm leading-6 text-white/70">{context === "plan" ? "Share this generated plan and your restrictions with a live coach. Choose your coach preferences and preferred time, then continue to PayPal." : "Choose an expert video review or request a live coaching session to talk through your set. Live sessions require a confirmed booking."}</p>
    {catalog.length > 0 && <ul className="mt-4 flex flex-wrap gap-2" aria-label="Coaching service prices">{catalog.filter(item => context !== "plan" || item.kind === "live_calls").map(item => <li key={item.id} className="rounded-xl border border-white/15 bg-black/20 px-3 py-2 text-xs leading-5">{item.name}<span className="ml-2 font-semibold text-teal">{usd(item.price_cents)}</span></li>)}</ul>}
    <Link href={href} className={buttonClass("primary", "mt-4")}>{context === "plan" ? "Ask a live coach" : "View coaching & payment options"}<ArrowRight size={15} aria-hidden /></Link>
    <p className="mt-3 text-xs leading-5 text-white/50">Optional one-time purchase · review the price before approving. {context === "plan" ? "Coach matching and availability require confirmation." : "Pay securely with PayPal."}</p>
  </section>;
}
