"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, LockKeyhole, Video } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { ModeBadge, PackageCard } from "./ReviewPrimitives";
import { SavedSuggestion } from "./SavedSuggestion";
import { api } from "@/lib/api";
import { questionForHuman } from "@/lib/coachChat";
import { commerceRequest, fieldClass, usd, type HandoffPreview, type ReviewCatalog, type ReviewIntake, type ReviewOrder, type ReviewRecording } from "@/lib/commerce";
import type { RecordedSet } from "@/lib/types";

export function HumanCoaching({ recordingId, previousOrderId, initialPackageId }: { recordingId: string; previousOrderId?: string; initialPackageId?: string }) {
  const router = useRouter();
  const [catalog, setCatalog] = useState<ReviewCatalog | null>(null);
  const [recording, setRecording] = useState<RecordedSet | null>(null);
  const [others, setOthers] = useState<ReviewRecording[]>([]);
  const [selected, setSelected] = useState<string[]>([recordingId]);
  const [question, setQuestion] = useState("");
  const [sharing, setSharing] = useState(false);
  const [preview, setPreview] = useState<HandoffPreview | null>(null);
  const [shareContext, setShareContext] = useState(false);
  const [packageId, setPackageId] = useState(initialPackageId || "day-coaching");
  const [saved, setSaved] = useState<{ intake: ReviewIntake; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    api.getRecording(recordingId).then(async rec => {
      const [c, conversation, recordings, context, previous] = await Promise.all([commerceRequest<ReviewCatalog>("/reviews/catalog"), api.coachConversation(rec.id), commerceRequest<ReviewRecording[]>("/reviews/recordings"), commerceRequest<HandoffPreview>(`/reviews/recordings/${rec.id}/handoff-context`), previousOrderId ? commerceRequest<ReviewOrder>(`/reviews/orders/${previousOrderId}`) : Promise.resolve(null)]);
      if (!alive) return;
      if (previous && (!previous.followup_available || !previous.sharing.recording_ids.includes(rec.id))) throw new Error("Additional support is available after your call or instructor notes, using a recording you choose to share again.");
      setRecording(rec); setCatalog(c); setError("");
      setPreview(context); setShareContext(false); setSharing(false); setSaved(null);
      setQuestion(current => current || questionForHuman(conversation.turns.at(-1), rec.id) || "I’d like to talk through this squat set and choose one focus for my next session.");
      setOthers(recordings.filter(r => r.id !== rec.id && r.synthetic === Boolean(rec.is_sample || rec.entry_source === "demo") && (r.has_video || r.synthetic)));
    }).catch(() => { if (alive) setError("We couldn’t open this recording and question. Return to My coach and choose your set again, or try loading it once more."); });
    return () => { alive = false; };
  }, [recordingId, previousOrderId, retry]);
  const mode = recording?.is_sample || recording?.entry_source === "demo" ? "simulated" : "sandbox";
  const chosen = catalog?.packages.find(p => p.id === packageId);
  const back = `/reviews?recording=${encodeURIComponent(recordingId)}`;
  function invalidate() { setSaved(null); }
  async function checkout() {
    setBusy(true); setError("");
    try {
      let request = saved;
      if (!request) {
        const intake = await commerceRequest<ReviewIntake>("/reviews/intakes", { question, recording_ids: selected, share_with_coach: sharing, ai_consent: false, mode, share_ai_context: shareContext, context_fingerprint: shareContext ? preview?.fingerprint : null, previous_order_id: previousOrderId || null });
        request = { intake, key: crypto.randomUUID() }; setSaved(request);
      }
      const order = await commerceRequest<ReviewOrder>("/reviews/orders", { intake_id: request.intake.id, package_id: packageId, checkout_key: request.key });
      router.push(`/reviews/${order.id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "Checkout couldn’t be prepared. Your clip and question are still selected; try again."); }
    finally { setBusy(false); }
  }
  const canBuy = Boolean(chosen && recording && (recording.has_video || mode === "simulated") && (mode === "sandbox" ? catalog?.sandbox_configured : catalog?.simulator_available));
  return <AppShell>
    <Link href={back} className="inline-flex min-h-11 items-center gap-2 text-sm text-white/65 hover:text-teal"><ArrowLeft size={15} aria-hidden />Back to my AI coach</Link>
    <header className="mt-5 max-w-2xl"><p className="font-mono text-[10px] uppercase tracking-[.2em] text-teal">Optional instructor session</p><h1 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">Make the next step yours.</h1><p className="mt-4 text-sm leading-7 text-white/60">Meet one-to-one with an instructor who can watch your movement, review the saved suggestion, and adapt the guidance to you. They can correct or disagree with the AI. Your AI feedback stays available before and after a purchase.</p></header>
    {error && <div role="alert" className="mt-5 rounded-xl border border-amber/25 p-4 text-sm leading-7 text-amber">{error}<Button variant="secondary" className="ml-3" onClick={() => setRetry(r => r + 1)}>Refresh sharing preview</Button></div>}
    {!catalog && !error && <p className="mt-8 text-sm text-white/50" role="status">Bringing your clip and question along…</p>}
    {catalog && recording && <>
      <details className="mt-5 text-xs text-white/50"><summary className="min-h-11 cursor-pointer py-3">Payment environment</summary><ModeBadge mode={mode} /></details>
      <div className="mt-6 grid items-start gap-7 lg:grid-cols-[1.1fr_1fr]">
        <div><h2 className="mb-4 text-sm font-medium text-white/70">Choose one-time support</h2>{catalog.packages.length === 0 && <p className="rounded-xl border border-white/10 p-5 text-sm leading-7 text-white/60">Instructor booking is being prepared. Keep using your saved feedback and AI coach; no purchase is required.</p>}<div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">{catalog.packages.filter(p => (p.family ? p.family === "instructor" : p.kind === "live_calls") && (previousOrderId || p.id !== "additional-session")).map(p => <PackageCard key={p.id} item={p} selected={p.id === packageId} onSelect={busy ? undefined : () => { setPackageId(p.id); invalidate(); }} />)}</div><div className="mt-5 flex gap-3 px-1"><Video size={18} className="mt-1 shrink-0 text-teal" aria-hidden /><p className="text-xs leading-6 text-white/50">Calls use a private external meeting link supplied by the coach after confirmation. Availability is confirmed by a person. No automatic renewal, embedded calling, or calendar connection.</p></div></div>
        <section className="rounded-2xl border border-white/10 bg-[#0e1218] p-5 sm:p-6" aria-label="Coaching checkout">
          <h2 className="text-lg font-semibold">Pick up where you left off.</h2>
          <div className="mt-5 flex gap-3 rounded-xl border border-teal/20 bg-teal/5 p-4"><Video className="mt-1 shrink-0 text-teal" size={18} aria-hidden /><div><p className="text-sm font-medium">{recording.exercise_name || "Selected squat"}{recording.set_index ? ` · Set ${recording.set_index}` : ""}</p><p className="mt-1 text-xs text-white/50">{recording.created_at && new Date(recording.created_at).toLocaleDateString()} · {mode === "simulated" ? "Synthetic example" : "Your selected recording"}</p><Link href={back} className="mt-2 inline-flex min-h-8 items-center text-xs text-teal underline">Replay and AI conversation</Link></div></div>
          {others.length > 0 && <details className="mt-4"><summary className="cursor-pointer py-2 text-xs text-white/55">Add one more clip (optional)</summary><div className="mt-2 max-h-40 space-y-2 overflow-auto">{others.map(r => <label key={r.id} className="flex gap-3 rounded-lg border border-white/10 p-3"><input type="checkbox" checked={selected.includes(r.id)} disabled={busy || (selected.length === 2 && !selected.includes(r.id))} onChange={e => { setSelected(e.target.checked ? [recordingId, r.id] : [recordingId]); setSharing(false); invalidate(); }} className="h-4 w-4 accent-teal" /><span className="text-xs text-white/65">Squat · set {r.set_index || "—"} · {new Date(r.created_at).toLocaleDateString()}</span></label>)}</div></details>}
          <label className="mt-5 block text-sm" htmlFor="human-question">Your question<textarea id="human-question" rows={3} maxLength={1200} className={fieldClass} value={question} disabled={busy} onChange={e => { setQuestion(e.target.value); setSharing(false); invalidate(); }} /></label>
          <p className="mt-2 text-[11px] leading-5 text-white/45">Carried from this set’s conversation. Earlier conversation history is not shared.</p>
          {preview?.context && <><SavedSuggestion context={preview.context} /><label className="mt-3 flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 p-4"><input type="checkbox" checked={shareContext} disabled={busy} onChange={e => { setShareContext(e.target.checked); setSharing(false); invalidate(); }} className="mt-1 h-4 w-4 shrink-0 accent-teal" /><span className="text-xs leading-6 text-white/75">Include the exact saved suggestion and latest answer shown above. This shares saved text with the instructor; it does not authorize new AI processing.</span></label></>}
          <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 p-4"><input type="checkbox" checked={sharing} disabled={busy} onChange={e => setSharing(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-teal" /><span className="text-xs leading-6 text-white/75">I consent to share {selected.length === 1 ? "this selected clip" : "these two selected clips"}, saved movement evidence, {shareContext ? "the displayed suggestion and latest answer, " : ""}and the question above with the instructor after confirmed payment. My other recordings and earlier conversation remain private.</span></label>
          <div className="mt-6 flex items-start justify-between gap-3 border-t border-white/10 pt-5"><div><p className="text-sm font-medium">{chosen?.name}</p><p className="mt-1 text-xs text-white/50">{chosen?.session_count} × {chosen?.session_minutes}-minute call{chosen?.session_count === 1 ? "" : "s"}</p></div><p className="text-2xl font-semibold">{chosen ? usd(chosen.price_cents) : ""}<span className="ml-1 text-[10px] font-normal text-white/50">USD</span></p></div>
          <p className="mt-3 text-xs leading-6 text-white/50">One payment. No automatic renewal. After payment, request a time in your local timezone; your coach confirms each appointment.</p>
          <Button className="mt-5 w-full" disabled={busy || !canBuy || !sharing || question.trim().length < 10} loading={busy} loadingLabel="Preparing checkout…" onClick={checkout}>{mode === "simulated" ? "Continue to practice checkout" : "Continue to PayPal"}<ArrowRight size={16} aria-hidden /></Button>
          {!canBuy && <p className="mt-3 text-xs leading-6 text-amber">{!recording.has_video && mode === "sandbox" ? "The original video is unavailable. Keep using the saved feedback, or choose an available recording to share." : "Checkout is temporarily unavailable. Your clip, question and saved feedback remain available."}</p>}
          <p className="mt-4 flex items-start gap-2 text-[11px] leading-6 text-white/45"><LockKeyhole size={13} className="mt-1 shrink-0" aria-hidden />Your coach sees only explicitly shared clips after payment. Meeting links are private to the athlete and authorized coach.</p>
          {catalog.merchant.toLowerCase().includes("fictional") && <p className="mt-3 text-[11px] leading-6 text-white/45">Example coaching service · appointments shown here are not live reservations.</p>}
        </section>
      </div>
    </>}
  </AppShell>;
}
