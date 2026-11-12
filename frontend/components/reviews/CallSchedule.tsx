"use client";

import { useState } from "react";
import { CalendarDays, ExternalLink, Video } from "lucide-react";
import { commerceRequest, fieldClass, type CoachingCall, type ReviewOrder } from "@/lib/commerce";
import { Button } from "@/components/ui/button";

function localInput(value: string) {
  const d = new Date(value);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
function timeLabel(value: string) {
  return new Date(value).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}
function localZone() { return Intl.DateTimeFormat().resolvedOptions().timeZone; }

export function CallSchedule({ order, coach = false, onChanged }: { order: ReviewOrder; coach?: boolean; onChanged: (o: ReviewOrder) => void }) {
  const [first, setFirst] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  if (order.package.kind !== "live_calls") return null;
  const active = order.payment_state === "paid";
  async function request() {
    setBusy(true); setError(""); setNotice("");
    try {
      onChanged(await commerceRequest<ReviewOrder>(`/reviews/orders/${order.id}/calls`, { starts_at: new Date(first).toISOString(), timezone: localZone() }));
      setNotice("Time request sent. Your coach will confirm each appointment and add a private meeting link.");
    } catch (e) { setError(e instanceof Error ? e.message : "Your time request couldn’t be saved. Try again."); }
    finally { setBusy(false); }
  }
  return <section className="rounded-2xl border border-teal/25 bg-teal/5 p-5 sm:p-6" aria-label="Video call schedule">
    <p className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-teal"><CalendarDays size={15} aria-hidden />Your video calls</p>
    <h2 className="mt-3 text-xl font-semibold">{coach ? "Confirm their time." : order.calls.length ? "Your schedule" : "Let’s find a time."}</h2>
    <p className="mt-3 text-sm leading-7 text-white/65">{order.package.session_count} × {order.package.session_minutes}-minute {order.package.session_count === 1 ? "call on your chosen day" : "calls, approximately weekly over one month"}. One-time purchase.</p>
    <p className="mt-2 text-[11px] leading-6 text-white/50">All times below are in {localZone().replaceAll("_", " ")} (your device’s timezone).</p>
    {order.mode === "simulated" && <p className="mt-3 text-xs leading-6 text-amber">Example appointment · no live booking is reserved.</p>}
    {!active && <p className="mt-4 text-sm leading-7 text-white/65">{order.payment_state === "refunded" ? "This purchase was refunded. Appointments are canceled and meeting links are no longer available." : order.payment_state === "refund_pending" ? "Your refund is being checked. Scheduling and meeting access are paused until its outcome is confirmed." : "Once payment is confirmed, you can request a preferred time here. Your coach will confirm availability."}</p>}
    {active && <>
      <div className="mt-5 space-y-4">{order.calls.map(call => <div key={call.id} className="rounded-xl border border-white/10 bg-[#0d1419] p-4">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="flex items-center gap-2 text-sm font-medium"><Video size={14} className="text-teal" aria-hidden />Call {call.session_index} of {order.package.session_count}</h3><span className={`text-[11px] ${call.status === "confirmed" ? "text-teal" : "text-white/50"}`}>{call.change_requested_at ? "Change requested" : call.status === "requested" ? "Requested · awaiting confirmation" : call.status === "canceled" ? "Time canceled" : call.status === "completed" ? "Completed" : "Confirmed"}</span></div>
        <dl className="mt-4 space-y-3 text-xs"><div><dt className="text-white/45">Athlete’s requested time</dt><dd className="mt-1 leading-6 text-white/70">{timeLabel(call.requested_at)}</dd>{coach && <dd className="text-[10px] text-white/40">Requested in {call.requested_timezone.replaceAll("_", " ")}</dd>}</div>{call.starts_at && call.status !== "canceled" && <div><dt className="text-teal/70">Confirmed appointment</dt><dd className="mt-1 text-sm leading-6 text-white">{timeLabel(call.starts_at)}</dd></div>}{call.change_requested_at && <div className="rounded-lg border border-amber/20 p-3"><dt className="text-amber">Requested replacement</dt><dd className="mt-1 leading-6 text-white/80">{timeLabel(call.change_requested_at)}</dd><dd className="mt-1 text-[11px] leading-6 text-white/50">The original appointment stays confirmed until the coach accepts a replacement.</dd></div>}</dl>
        {call.meeting_url && <a href={call.meeting_url} target="_blank" rel="noopener noreferrer" className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-full border border-teal/30 px-4 text-sm text-teal">Join confirmed video call<ExternalLink size={14} aria-hidden /></a>}
        {call.status === "requested" && !coach && <p className="mt-3 text-[11px] leading-6 text-white/50">Your preferred time is a request, not a reservation. The coach will confirm it and add a meeting link.</p>}
        {call.status === "canceled" && <p className="mt-3 text-xs leading-6 text-white/55">Your purchased call remains available. Request a new time below.</p>}
        {coach ? <CoachCall key={`${call.id}-${call.starts_at}-${call.change_requested_at}-${call.status}`} call={call} order={order} onChanged={onChanged} /> : <AthleteCall key={`${call.id}-${call.requested_at}-${call.change_requested_at}-${call.status}`} call={call} order={order} onChanged={onChanged} />}
      </div>)}</div>
      {!coach && !order.calls.length && <form className="mt-5 border-t border-white/10 pt-5" onSubmit={e => { e.preventDefault(); void request(); }}><label className="block text-sm">{order.package.session_count === 4 ? "Preferred time for your first call" : "Preferred call time"}<input type="datetime-local" required value={first} onChange={e => setFirst(e.target.value)} className={fieldClass} disabled={busy} /></label><p className="mt-2 text-[11px] leading-6 text-white/50">At least one hour ahead, within the next 90 days.{order.package.session_count === 4 ? " The following three calls are requested a week apart in your timezone. Each can be changed individually, within a month of the first request." : " Your coach confirms availability."}</p><Button className="mt-4 w-full" type="submit" disabled={busy || !first} loading={busy}>Request preferred time</Button></form>}
      {coach && !order.calls.length && <p className="mt-4 text-sm text-white/55">Waiting for the athlete’s preferred time.</p>}
    </>}
    {error && <p role="alert" className="mt-4 text-sm leading-6 text-amber">{error}</p>}
    {notice && <p role="status" className="mt-4 text-sm leading-6 text-teal">{notice}</p>}
    <Button className="mt-4" variant="ghost" onClick={async () => { setError(""); try { onChanged(await commerceRequest<ReviewOrder>(coach ? `/coach/tasks/${order.task!.id}` : `/reviews/orders/${order.id}`)); } catch (e) { setError(e instanceof Error ? e.message : "Your schedule couldn’t refresh. Try again."); } }}>Refresh schedule</Button>
    <p className="mt-3 text-[10px] leading-6 text-white/40">Your private meeting link appears here after your coach confirms the appointment.</p>
  </section>;
}

function AthleteCall({ call, order, onChanged }: { call: CoachingCall; order: ReviewOrder; onChanged: (o: ReviewOrder) => void }) {
  const [open, setOpen] = useState(false);
  const [starts, setStarts] = useState(localInput(call.change_requested_at || call.starts_at || call.requested_at));
  const [cancel, setCancel] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (call.status === "completed") return null;
  async function submit(canceling = false) {
    setBusy(true); setError("");
    try { onChanged(await commerceRequest<ReviewOrder>(`/reviews/orders/${order.id}/calls/${call.id}/${canceling ? "cancel" : "request"}`, canceling ? {} : { starts_at: new Date(starts).toISOString(), timezone: localZone() })); setOpen(false); setCancel(false); }
    catch (e) { setError(e instanceof Error ? e.message : "Your change couldn’t be saved. Try again."); }
    finally { setBusy(false); }
  }
  return <div className="mt-3">
    <Button className="w-full" variant="ghost" disabled={busy} onClick={() => setOpen(!open)}>{open ? "Keep current time" : call.status === "canceled" ? "Request a new time" : call.status === "confirmed" ? "Request a time change" : "Change preferred time"}</Button>
    {open && <form className="mt-3" onSubmit={e => { e.preventDefault(); void submit(); }}><label className="block text-xs">New preferred time<input type="datetime-local" value={starts} onChange={e => setStarts(e.target.value)} required className={fieldClass} disabled={busy} /></label><Button type="submit" className="mt-3 w-full" disabled={busy || !starts} loading={busy}>Send time request</Button></form>}
    {call.status !== "canceled" && (cancel ? <div className="mt-3 rounded-lg border border-amber/25 p-3"><p className="text-xs leading-6 text-white/65">Cancel this appointment time? Your purchased call stays available to schedule again. This does not refund the payment.</p><div className="mt-3 flex flex-wrap gap-2"><Button variant="secondary" disabled={busy} onClick={() => void submit(true)}>Cancel this time</Button><Button variant="ghost" disabled={busy} onClick={() => setCancel(false)}>Keep appointment</Button></div></div> : <button type="button" className="mt-2 min-h-11 text-xs text-white/45 hover:text-white" disabled={busy} onClick={() => setCancel(true)}>Cancel appointment time</button>)}
    {error && <p role="alert" className="mt-3 text-xs leading-6 text-amber">{error}</p>}
  </div>;
}

function CoachCall({ call, order, onChanged }: { call: CoachingCall; order: ReviewOrder; onChanged: (o: ReviewOrder) => void }) {
  const [starts, setStarts] = useState(localInput(call.change_requested_at || call.starts_at || call.requested_at));
  const [url, setUrl] = useState(call.meeting_url || "");
  const [openedAt] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(complete = false) {
    setBusy(true); setError("");
    try { onChanged(await commerceRequest<ReviewOrder>(`/coach/tasks/${order.task!.id}/calls/${call.id}/${complete ? "complete" : "confirm"}`, complete ? {} : { starts_at: new Date(starts).toISOString(), meeting_url: url, timezone: localZone() })); }
    catch (e) { setError(e instanceof Error ? e.message : "The appointment couldn’t be saved. Try again."); }
    finally { setBusy(false); }
  }
  if (["completed", "canceled"].includes(call.status)) return null;
  return <form className="mt-4 border-t border-white/10 pt-4" onSubmit={e => { e.preventDefault(); void submit(); }}><label className="block text-xs">Confirm date and time<input type="datetime-local" value={starts} onChange={e => setStarts(e.target.value)} required disabled={busy} className={fieldClass} /></label><label className="mt-3 block text-xs">Private meeting link<input type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://meet.google.com/…" required disabled={busy} className={fieldClass} /></label><p className="mt-2 text-[11px] leading-6 text-white/50">Use a Google Meet, Zoom or Microsoft Teams link created for this appointment. It is shared only with this athlete.</p><Button type="submit" className="mt-3 w-full" disabled={busy} loading={busy}>{call.status === "confirmed" ? "Confirm updated appointment" : "Confirm call & share link"}</Button>{call.status === "confirmed" && <Button className="mt-2 w-full" variant="secondary" type="button" disabled={busy || !call.starts_at || new Date(call.starts_at).getTime() > openedAt} onClick={() => void submit(true)}>Mark call completed</Button>}{error && <p role="alert" className="mt-3 text-xs leading-6 text-amber">{error}</p>}</form>;
}
