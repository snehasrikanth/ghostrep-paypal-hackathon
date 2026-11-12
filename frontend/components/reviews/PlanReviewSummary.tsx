import type { PlanReviewContext } from "@/lib/commerce";

function SharedDetails({ value }: { value: unknown }) {
  if (value == null || value === "") return <span>Not specified</span>;
  if (Array.isArray(value)) return value.length ? <ul className="space-y-2 border-l border-white/15 pl-3">{value.map((item, i) => <li key={i}><SharedDetails value={item} /></li>)}</ul> : <span>None specified</span>;
  if (typeof value === "object") return <dl className="space-y-3">{Object.entries(value).map(([key, item]) => <div key={key}><dt className="capitalize text-white/50">{key.replaceAll("_", " ")}</dt><dd className="mt-1"><SharedDetails value={item} /></dd></div>)}</dl>;
  return <span>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value).replaceAll("_", " ")}</span>;
}

export function PlanReviewSummary({ context }: { context: PlanReviewContext }) {
  const prefs = context.preferences;
  const experience: Record<string, string> = { any: "Any experience level", "3_plus": "3+ years", "5_plus": "5+ years", "10_plus": "10+ years" };
  const specialty: Record<string, string> = { general: "Plan and exercise selection", beginner: "Beginner training", strength: "Strength and squat technique", mobility: "Mobility and movement", adapted_training: "Adapting training to restrictions" };
  return <section className="rounded-2xl border border-teal/25 bg-teal/5 p-5" aria-label="Shared plan review">
    <p className="text-xs uppercase tracking-wider text-teal">Plan for coach review</p>
    <h2 className="mt-2 text-xl font-semibold">{context.plan.name}</h2>
    <p className="mt-3 text-sm leading-6 text-white/75">Restrictions: {context.restrictions.length ? context.restrictions.join(" · ") : "None saved"}</p>
    {prefs && <><p className="mt-3 text-sm leading-6 text-white/75">Coach preferences: {prefs.gender === "no_preference" ? "Any gender" : prefs.gender} · {prefs.nationality} · {prefs.language} · {experience[prefs.experience] || prefs.experience} · {specialty[prefs.specialty] || prefs.specialty}</p><p className="mt-2 text-xs leading-6 text-teal">Preferred time at checkout: {new Date(prefs.preferred_at).toLocaleString(undefined, { timeZone: prefs.timezone })} ({prefs.timezone}) · see the schedule for current confirmation</p></>}
    <details className="mt-4"><summary className="min-h-11 cursor-pointer py-3 text-sm text-teal">Review shared exercises, schedule & training preferences</summary>
      <ul className="space-y-3 text-sm leading-6">{context.plan.exercises.map((ex,i) => <li key={i}>{ex.name} · {ex.sets} sets × {ex.target_reps} reps · {ex.rest_seconds}s rest{ex.notes && <p className="text-xs text-white/60">{ex.notes}</p>}</li>)}</ul>
      {context.plan.notes && <p className="mt-3 whitespace-pre-wrap text-sm leading-6">{context.plan.notes}</p>}
      <div className="mt-4 max-h-80 overflow-auto text-xs leading-6 text-white/75"><SharedDetails value={{ schedule: context.plan.schedule, training_preferences: context.training_preferences }} /></div>
    </details>
    <p className="mt-3 text-xs leading-6 text-white/50">A saved copy is shared when you consent. Matching and session time require coach confirmation. No recording is required.</p>
  </section>;
}
