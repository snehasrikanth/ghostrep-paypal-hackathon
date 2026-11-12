import { CheckCircle2, Circle, Clock3 } from "lucide-react";
import type { ReviewOrder } from "@/lib/commerce";
import { purchaseJourney } from "@/lib/purchaseJourney";

export function PurchaseJourney({ order }: { order: ReviewOrder }) {
  return <section aria-label="Purchase and delivery progress" className="mt-6 rounded-2xl border border-white/15 p-5"><h2 className="text-sm font-semibold">Your purchase, step by step</h2><ol className="mt-4 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">{purchaseJourney(order).map((step,i) => <li key={step.label} aria-current={step.state === "current" ? "step" : undefined} className={step.state === "stopped" ? "text-white/45" : step.state === "done" || step.state === "current" ? "text-teal" : "text-white/50"}><p className="flex items-start gap-2 text-xs font-medium">{step.state === "done" ? <CheckCircle2 size={16} className="shrink-0" aria-hidden /> : step.state === "current" ? <Clock3 size={16} className="shrink-0" aria-hidden /> : <Circle size={16} className="shrink-0" aria-hidden />}<span>{i+1}. {step.label}</span></p><p className="mt-2 text-xs leading-6 text-white/60">{step.detail}</p></li>)}</ol></section>;
}
