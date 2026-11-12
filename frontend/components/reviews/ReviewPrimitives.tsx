import { serviceText } from "@/lib/commerceCopy";
import Link from "next/link";
import { ArrowUpRight, Check, ShieldCheck } from "lucide-react";
import { stateLabel, usd, type ReviewOrder, type ReviewPackage } from "@/lib/commerce";

export function ModeBadge({ mode }: { mode: string }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 font-mono text-[10px] font-medium uppercase tracking-wider ${mode === "simulated" ? "border-amber/30 bg-amber/10 text-amber" : "border-teal/25 bg-teal/8 text-teal"}`}><ShieldCheck size={12} aria-hidden />{mode === "simulated" ? "Practice checkout · no charge" : "Test payments"}</span>;
}

export function PackageCard({ item, selected, onSelect }: { item: ReviewPackage; selected?: boolean; onSelect?: () => void }) {
  return <div className={`relative flex h-full flex-col rounded-2xl border p-5 ${selected ? "border-teal/70 bg-teal/5" : "border-white/10 bg-white/[0.025]"}`}>
    <div className="mb-4 flex items-start justify-between gap-3"><span className="rounded-lg border border-white/10 px-2.5 py-1 font-mono text-xs text-white/65">{item.id === "additional-session" ? "ADDITIONAL SESSION" : item.family === "agentic" ? (item.kind === "ai_report" ? "TECHNIQUE REPORT" : item.kind === "live_calls" ? "LIVE SESSION" : "EXPERT REVIEW") : item.kind === "live_calls" ? item.session_count === 4 ? "ONE MONTH" : "ONE SESSION" : `${item.clip_count} CLIP${item.clip_count > 1 ? "S" : ""}`}</span><span className="font-display text-2xl font-semibold">{usd(item.price_cents)}<span className="ml-1 text-xs font-normal text-white/50">USD</span></span></div>
    <h3 className="text-lg font-semibold">{item.name}</h3><p className="mt-2 text-sm leading-6 text-white/65">{serviceText(item.description)}</p>
    <ul className="my-5 space-y-2.5">{item.deliverables.map(d => <li key={d} className="flex items-start gap-2 text-xs leading-5 text-white/80"><Check className="mt-0.5 shrink-0 text-teal" size={14} aria-hidden />{serviceText(d)}</li>)}</ul>
    <p className="mt-auto text-[11px] text-white/45">{serviceText(item.delivery_label) || (item.kind === "live_calls" ? `${item.session_count} video call${item.session_count === 1 ? "" : "s"} · ${item.session_minutes} min each · paid once` : item.kind === "ai_report" ? "AI-generated feedback · not a live coach" : "Written feedback on your selected clips")}</p>
    {onSelect && <button type="button" onClick={onSelect} aria-pressed={selected} aria-label={`Choose ${item.name}`} className={`mt-4 min-h-11 rounded-full border px-4 text-sm hover:border-teal hover:text-teal ${selected ? "border-teal/50 text-teal" : "border-white/20"}`}>{selected ? "Selected for checkout" : "Choose this plan"}</button>}
  </div>;
}

export function OrderLink({ order, coach = false }: { order: ReviewOrder; coach?: boolean }) {
  return <Link href={coach ? `/coach/${order.task?.id}` : `/reviews/${order.id}`} className="group flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/[0.02] p-4 transition hover:border-teal/40">
    <div className="min-w-0"><p className="text-sm font-medium">{order.package.name}</p><p className="mt-1 truncate text-xs text-white/60">{order.question}</p><p className="mt-2 text-xs text-teal">{stateLabel(order.task?.status || order.payment_state)} · {usd(order.amount_cents)} · {order.mode === "simulated" ? "Practice" : "PayPal"}</p></div><ArrowUpRight size={18} className="shrink-0 text-white/40 group-hover:text-teal" aria-hidden />
  </Link>;
}
