"use client";

import Link from "next/link";
import { useState } from "react";
import { Camera, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { commerceRequest } from "@/lib/commerce";
import type { WorkoutPlan } from "@/lib/types";

export function BarbellSquatCheck({ plan, onChanged }: { plan: WorkoutPlan; onChanged?: (plan: WorkoutPlan) => void }) {
  const [access, setAccess] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const check = plan.analysis_requirement;
  if (!check) return null;
  async function addCheck() {
    setBusy(true); setError("");
    try { onChanged?.(await commerceRequest<WorkoutPlan>(`/workouts/${encodeURIComponent(plan.id)}/barbell-check`, { confirm_barbell_access: access })); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not add the check-in. Your logged sets are saved."); }
    finally { setBusy(false); }
  }
  return <section aria-label="Barbell squat analysis readiness" className={`mt-4 rounded-2xl border p-4 sm:p-5 ${check.included ? "border-teal/25 bg-teal/5" : "border-white/15 bg-card"}`}>
    <p className="flex items-center gap-2 text-sm font-semibold text-teal">{check.included ? <CheckCircle2 size={18} aria-hidden /> : <Camera size={18} aria-hidden />}Barbell squat video check-in</p>
    <p className="mt-2 text-sm leading-6 text-white/80">{check.included ? "Included in this workout. Record a barbell squat set for rep-by-rep analysis; your other lifts stay in the training log." : check.status === "equipment_required" ? "Record and log this workout with your current equipment. Automated rep analysis is available for barbell squat sets only." : check.reason}</p>
    {!check.included && onChanged && ["equipment_required", "ready_to_add"].includes(check.status) && ["active", "proposed"].includes(plan.status) && <details className="mt-3" open={check.status === "ready_to_add"}><summary className="min-h-11 cursor-pointer py-3 text-xs text-white/60">{check.status === "equipment_required" ? "Equipment changed? Add a barbell check-in" : "Add your video check-in"}</summary>
      {check.status === "equipment_required" && <label className="mt-3 flex items-start gap-3 text-xs leading-6 text-white/75"><input type="checkbox" checked={access} disabled={busy} onChange={e => setAccess(e.target.checked)} className="mt-1 h-5 w-5 shrink-0 accent-teal" />I have access to a barbell and squat rack. Save this equipment in my profile.</label>}
      <Button className="mt-3" variant="secondary" disabled={busy || (check.status === "equipment_required" && !access)} loading={busy} onClick={addCheck}>Add barbell squat check-in</Button>
      <p className="mt-2 text-xs leading-6 text-white/50">Adds one technique set without prescribing a load. Your existing exercises and logged sets stay saved.</p>
    </details>}
    {!check.included && ["restricted", "coach_setup"].includes(check.status) && <Link href={`/reviews?plan=${encodeURIComponent(plan.id)}`} className="mt-2 inline-flex min-h-11 items-center text-sm text-teal">Review this with a live coach →</Link>}
    {error && <p role="alert" className="mt-3 text-sm text-amber">{error}</p>}
  </section>;
}
