"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowUpRight, Check, Play, RefreshCw, Video } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { CoachChat } from "@/components/analysis/CoachChat";
import { GhostPlayer, type SeekCue } from "@/components/ghost/GhostPlayer";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { coachingForDisplay, detectedRepCount, mainFinding, nextSetAction } from "@/lib/coaching";
import type { Analysis, Coaching, Overlay, RecordedSet } from "@/lib/types";

const noTime = () => {};
const terminal = new Set(["COMPLETED", "SAVED", "LOGGED", "FAILED"]);

export function RecordingCoach({ recordingId }: { recordingId: string }) {
  const [recording, setRecording] = useState<RecordedSet | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [coaching, setCoaching] = useState<Coaching | null>(null);
  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [error, setError] = useState("");
  const [mediaError, setMediaError] = useState(false);
  const [retry, setRetry] = useState(0);
  const [rep, setRep] = useState<number | null>(null);
  const [seek, setSeek] = useState<SeekCue | null>(null);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const rec = await api.getRecording(recordingId);
        if (!alive) return;
        setRecording(rec); setError("");
        if (rec.processing_status === "COMPLETED" && rec.has_analysis) {
          const [a, o, c] = await Promise.all([api.getAnalysis(rec.id), api.getOverlay(rec.id), api.getCoaching(rec.id).catch(() => null)]);
          if (!alive) return;
          setAnalysis(a); setOverlay(o); setCoaching(c ? coachingForDisplay(a, c) : null);
        } else if (!terminal.has(rec.processing_status)) timer = setTimeout(load, 2000);
      } catch (e) {
        if (alive) setError(e instanceof ApiError && e.status === 404
          ? "This recording isn’t available in this browser. It may have been removed or belong to another athlete."
          : "Your recording couldn’t load. Check your connection and try again; your saved set hasn’t changed.");
      }
    }
    void load();
    return () => { alive = false; clearTimeout(timer); };
  }, [recordingId, retry]);
  const sample = recording?.is_sample || recording?.entry_source === "demo";
  const finding = analysis ? mainFinding(analysis, coaching) : null;
  const nextStep = coaching?.user_decision === "pending"
    ? nextSetAction(coaching).text
    : finding?.repId && analysis?.reference_rep && finding.repId !== analysis.reference_rep
      ? `Replay rep ${finding.repId}, then your reference rep ${analysis.reference_rep}. Compare the saved measurements before changing your next set.`
      : "Review the replay and saved evidence before changing your next set.";
  const processing = recording && !terminal.has(recording.processing_status);
  function replay(seconds: number, repId: number) {
    setRep(repId); setSeek(s => ({ t: seconds, key: (s?.key || 0) + 1 }));
  }
  return <AppShell>
    <div className="flex flex-wrap items-center justify-between gap-3"><Link href="/reviews" className="inline-flex min-h-11 items-center gap-2 text-sm text-white/65 hover:text-teal"><ArrowLeft size={15} aria-hidden />My coach</Link><Link href="/record" className="inline-flex min-h-11 items-center gap-2 text-sm text-teal"><Video size={15} aria-hidden />Record a set</Link></div>
    {error && <div role="alert" className="mt-6 max-w-2xl rounded-2xl border border-amber/25 bg-amber/5 p-6"><h1 className="text-xl font-semibold">Let’s get you back to your set.</h1><p className="mt-3 text-sm leading-7 text-white/70">{error}</p><div className="mt-5 flex flex-wrap gap-3"><Button variant="secondary" onClick={() => setRetry(r => r + 1)}>Try again</Button><Link href="/reviews" className="inline-flex min-h-11 items-center px-3 text-sm text-teal">Choose a recent set</Link></div></div>}
    {!recording && !error && <div className="mt-8 animate-pulse space-y-5" role="status"><p className="text-sm text-white/55">Opening your recording and saved feedback…</p><div className="aspect-video max-w-3xl rounded-2xl bg-white/5" /></div>}
    {recording && <>
      <header className="mt-5 mb-7"><p className="font-mono text-[10px] uppercase tracking-[.2em] text-teal">Movement feedback</p><h1 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-4xl">{recording.exercise_name || recording.exercise_id.replaceAll("_", " ")}{recording.set_index ? <span className="font-normal text-white/45"> · Set {recording.set_index}</span> : ""}</h1><div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-white/55"><time dateTime={recording.created_at || undefined}>{recording.created_at ? new Date(recording.created_at).toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "Recording date unavailable"}</time><span className="text-white/80">{analysis ? `${detectedRepCount(analysis)} ${sample ? "example" : "measured"} reps` : "No measured rep count"}</span>{recording.completed_reps !== null && <span>{recording.completed_reps} {sample ? "example" : "user-logged"} reps</span>}{sample && <span className="rounded-full border border-amber/25 px-2 py-1 text-amber">Sample recording</span>}</div></header>
      {sample && <p className="mb-5 rounded-xl border border-amber/20 bg-amber/5 px-4 py-3 text-xs leading-6 text-amber">Sample movement and example feedback. This recording is separate from your own training.</p>}
      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-5">
          <section id="set-replay" tabIndex={-1} aria-label="Selected recording replay" className="scroll-mt-28 overflow-hidden rounded-2xl border border-white/10 bg-[#0c1015] p-3 sm:p-4">
            <div className="mb-3 flex items-center justify-between px-1"><h2 className="text-sm font-medium">Your replay</h2><span className="text-[11px] text-white/45">{recording.duration_seconds ? `${Math.round(recording.duration_seconds)} seconds` : "Saved set"}</span></div>
            {overlay ? <GhostPlayer overlay={overlay} setId={recording.id} seekTo={seek} onTime={noTime} /> : recording.has_video && !mediaError ? <video src={api.mediaUrl(recording.id)} className="aspect-video w-full rounded-xl bg-black object-contain" controls playsInline preload="metadata" aria-label={`${recording.exercise_name || "Selected set"} video`} onError={() => setMediaError(true)} /> : <div className="flex aspect-video flex-col items-center justify-center rounded-xl bg-black px-6 text-center"><Video className="mb-3 text-white/40" size={30} aria-hidden /><p className="text-sm text-white/70">{processing ? "Your clip is being prepared." : "The original video is no longer available."}</p><p className="mt-2 max-w-md text-xs leading-6 text-white/45">{processing ? "You can return later; this page will check for saved results." : "Any saved evidence and conversations remain private and available below."}</p></div>}
            {!sample && !recording.has_video && overlay && <p className="mt-3 text-xs leading-6 text-amber">Original video unavailable. This is the saved movement trace from your analysis.</p>}
            {analysis && <><div className="mt-4 flex flex-wrap gap-2" aria-label="Replay a measured rep">{analysis.reps.map(r => <button type="button" key={r.rep_id} onClick={() => replay(r.start_seconds, r.rep_id)} aria-pressed={rep === r.rep_id} className={`inline-flex min-h-11 items-center gap-1.5 rounded-lg border px-3 text-xs ${rep === r.rep_id ? "border-teal/60 bg-teal/10 text-teal" : "border-white/10 text-white/70 hover:border-teal/40"}`}><Play size={11} aria-hidden />Rep {r.rep_id}{r.is_reference ? <span className="text-teal"> · reference</span> : ""}</button>)}</div><p className="mt-3 px-1 text-[11px] leading-5 text-white/45">Tap a rep to replay its saved timestamp. Your personal reference is an observed rep, not certified ideal technique.</p></>}
          </section>
          <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#0e1218]" aria-label="Movement feedback">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/8 px-5 py-4"><h2 className="text-base font-semibold">A useful place to start</h2><span className="text-[10px] text-white/45">{sample ? "Sample movement" : coaching?.source === "muse_spark" ? "Saved AI interpretation · Muse Spark" : coaching?.source === "fixture" ? "Saved sample interpretation" : "Saved local interpretation"}</span></div>
            {finding ? <div className="divide-y divide-white/8">
              <FeedbackStep number="01" title="What we noticed"><p>{finding.what}</p>{finding.kind === "difference" && <p className="mt-2 text-xs text-white/45">A difference from your own reference, not a verdict about correct technique.</p>}</FeedbackStep>
              <FeedbackStep number="02" title="The moment behind it">{finding.seconds !== null && finding.repId !== null ? <><p>{finding.where}</p><button className="mt-3 inline-flex min-h-11 items-center gap-2 text-sm text-teal" onClick={() => replay(finding.seconds!, finding.repId!)}><Play size={13} aria-hidden />Replay rep {finding.repId}</button></> : <p>{analysis!.reference_rep ? `Start with rep ${analysis!.reference_rep}, your saved personal reference. No specific difference is established.` : "No reliable rep-linked movement finding was saved. Review the original clip before drawing conclusions."}</p>}</FeedbackStep>
              <FeedbackStep number="03" title="One practical next step"><p>{nextStep}</p>{coaching?.reason && <details className="mt-3 text-xs leading-6 text-white/55"><summary className="cursor-pointer py-2 text-white/70">Why this step · saved interpretation</summary><p className="mt-2">{coaching.reason}</p></details>}<p className="mt-2 text-xs text-white/45">Review guidance. Your workout targets have not been changed here.</p></FeedbackStep>
            </div> : <div className="px-5 py-5"><p className="text-sm leading-7 text-white/75">{processing ? "Movement feedback is still being prepared. Your results will appear when processing finishes." : recording.processing_status === "FAILED" ? "This clip couldn’t be analyzed. Try a clear side view with your whole body in frame." : "This video was saved without completed movement analysis. Replay it, review your logged set, or ask about the evidence that is available."}</p><Link href={`/recordings/${recording.id}`} className="mt-4 inline-flex min-h-11 items-center gap-2 text-sm text-teal">Open recording details<ArrowUpRight size={14} aria-hidden /></Link>{processing && <Button className="mt-3" variant="ghost" onClick={() => setRetry(r => r + 1)}><RefreshCw size={14} aria-hidden />Check processing</Button>}</div>}
          </section>
          <div className="flex flex-wrap items-center justify-between gap-3 px-1"><p className="max-w-lg text-[11px] leading-6 text-white/40">Measurements, model interpretation and human advice are different sources. Video feedback does not assess injury risk.</p>{analysis && <Link href={`/analysis/${recording.id}`} className="inline-flex min-h-11 shrink-0 items-center gap-1 text-xs text-teal">Full analysis<ArrowUpRight size={13} aria-hidden /></Link>}</div>
        </div>
        <aside className="min-w-0 xl:sticky xl:top-[calc(var(--app-header-height)+1.5rem)]"><div className="mb-3 flex items-center gap-2 px-1 text-xs text-white/50"><Check size={13} className="text-teal" aria-hidden />Available before any purchase</div><CoachChat key={recording.id} setId={recording.id} exerciseId={recording.exercise_id} selectedRep={rep} onReplay={replay} defaultOpen /></aside>
      </div>
    </>}
  </AppShell>;
}

function FeedbackStep({ number, title, children }: { number: string; title: string; children: React.ReactNode }) {
  return <div className="flex gap-4 px-5 py-5"><span className="pt-0.5 font-mono text-[10px] text-teal/65">{number}</span><div className="min-w-0"><h3 className="text-xs font-semibold text-white/85">{title}</h3><div className="mt-2 text-sm leading-7 text-white/65">{children}</div></div></div>;
}
