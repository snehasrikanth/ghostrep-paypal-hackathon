"use client";
import { useEffect, useState } from "react";
import { GhostPlayer } from "@/components/ghost/GhostPlayer";
import { commerceBase, commerceRequest, type SharedClip } from "@/lib/commerce";

const noTime = () => {};
export function ReviewReplay({ prefix }: { prefix: string }) {
  const [clips, setClips] = useState<SharedClip[]>([]);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [seek, setSeek] = useState<Record<string, { t: number; key: number }>>({});
  useEffect(() => { let alive = true; commerceRequest<SharedClip[]>(`${prefix}/clips`).then(c => { if (alive) { setClips(c); setError(""); } }).catch(e => { if (alive) setError(e.message); }); return () => { alive = false; }; }, [prefix, retry]);
  if (error) return <div role="alert" className="rounded-xl border border-amber/25 p-4 text-sm text-amber">{error}<button className="ml-3 underline" onClick={() => setRetry(r => r + 1)}>Retry replay</button></div>;
  if (!clips.length) return <p role="status" className="text-sm text-white/65">Loading shared replay…</p>;
  return <div className="space-y-6">{clips.map((clip, index) => <section key={clip.recording_id} className="overflow-hidden rounded-2xl border border-white/10 bg-black/20 p-4">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-semibold">Selected squat clip {index + 1}</h3><span className="font-mono text-[10px] uppercase tracking-wide text-white/50">{clip.synthetic ? "Sample movement" : "Athlete recording"}</span></div>
    {clip.overlay ? <GhostPlayer overlay={clip.overlay} setId={clip.recording_id} mediaSource={clip.has_video ? `${commerceBase}${prefix}/clips/${clip.recording_id}/media` : ""} seekTo={seek[clip.recording_id]} onTime={noTime} /> : clip.has_video ? <video className="aspect-video w-full rounded-xl bg-black" src={`${commerceBase}${prefix}/clips/${clip.recording_id}/media`} controls playsInline preload="metadata" aria-label={`Selected clip ${index + 1}`} /> : <p className="py-10 text-center text-sm text-white/65">Video deleted. Saved evidence and your receipt are retained.</p>}
    {clip.synthetic && <p className="mt-3 text-xs leading-5 text-amber">Illustrated movement example. This is not your recorded video.</p>}
    <div className="mt-3 flex flex-wrap gap-2">{clip.reps.map(rep => <button key={rep.rep_index} type="button" onClick={() => setSeek(s => ({ ...s, [clip.recording_id]: { t: rep.start_seconds, key: Date.now() } }))} className="min-h-11 rounded-lg border border-white/15 px-3 text-xs hover:border-teal hover:text-teal">Rep {rep.rep_index}{rep.is_reference ? " · reference" : ""}</button>)}</div>
    <p className="mt-3 text-[11px] leading-5 text-white/55">A personal reference is an observed rep, not certified ideal technique. Rep links use saved timestamps.</p>
    <details className="mt-4 border-t border-white/10 pt-3"><summary className="cursor-pointer text-xs text-white/75">Saved evidence · observations, not coach advice</summary><ul className="mt-3 space-y-2">{Object.entries(clip.facts).map(([key, value]) => <li className="text-xs leading-6 text-white/65" key={key}>{value.text}</li>)}</ul></details>
  </section>)}</div>;
}
