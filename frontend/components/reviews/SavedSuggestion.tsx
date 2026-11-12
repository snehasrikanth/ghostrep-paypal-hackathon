import type { SharedCoachingContext } from "@/lib/commerce";

export function SavedSuggestion({ context, frozen = false }: { context: SharedCoachingContext; frozen?: boolean }) {
  const saved = context.suggestion;
  const answer = context.latest_answer;
  const source = saved?.source_label || (saved?.source === "muse_spark" || saved?.source === "meta_live" ? "Saved AI interpretation" : "Saved training feedback");
  return <section aria-label="Saved coaching context" className="mt-5 rounded-xl border border-teal/20 bg-teal/5 p-4">
    <h3 className="text-sm font-semibold">{frozen ? "Shared coaching context" : "The context you can share"}</h3>
    <p className="mt-2 text-[11px] leading-6 text-white/50">{frozen ? "A saved copy from the moment you consented. Later AI answers do not change this purchase." : "Only the suggestion and latest answer shown here can be included. Earlier chat and other recordings stay private."}</p>
    {saved && <div className="mt-4 border-t border-white/10 pt-3"><p className="text-[10px] text-teal">{source}</p><p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-white/85">{saved.summary}</p>{saved.reason && <p className="mt-2 whitespace-pre-wrap text-xs leading-6 text-white/65">{saved.reason}</p>}<dl className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-white/60">{saved.suggested_reps != null && <div><dt>Suggested reps</dt><dd className="mt-1 text-white/85">{saved.suggested_reps}</dd></div>}{saved.suggested_rest_seconds != null && <div><dt>Suggested rest</dt><dd className="mt-1 text-white/85">{saved.suggested_rest_seconds} seconds</dd></div>}{saved.suggested_load_kg != null && <div><dt>Suggested load</dt><dd className="mt-1 text-white/85">{saved.suggested_load_kg} kg</dd></div>}</dl>{saved.actionable === false && <p className="mt-3 text-[11px] leading-6 text-white/50">Saved for review; this suggestion cannot currently change workout targets.</p>}</div>}
    {answer && <details className="mt-4 border-t border-white/10 pt-3"><summary className="cursor-pointer py-2 text-xs text-white/80">Latest answer · {answer.source === "muse_spark" ? "AI coach" : "saved-evidence summary"}</summary><p className="mt-2 whitespace-pre-wrap text-xs leading-6 text-white/60">Your question: {answer.question}</p><p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-white/80">{answer.answer}</p>{answer.uncertainty && <p className="mt-3 text-xs leading-6 text-white/55">{answer.uncertainty}</p>}</details>}
    <p className="mt-4 text-[11px] leading-6 text-white/55">An instructor can explain, correct or disagree with this suggestion after reviewing your movement.</p>
  </section>;
}
