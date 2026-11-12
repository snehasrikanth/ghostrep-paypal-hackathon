"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { ActionFeedback } from "@/components/ui/ActionFeedback";
import { OrderLink } from "@/components/reviews/ReviewPrimitives";
import { commerceRequest, fieldClass, type ReviewCatalog, type ReviewOrder } from "@/lib/commerce";

export default function CoachPage() {
  const [session, setSession] = useState<{ identity: string; demo: boolean } | null>(null);
  const [tasks, setTasks] = useState<ReviewOrder[]>([]);
  const [password, setPassword] = useState("");
  const [demo, setDemo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  async function load() {
    const s = await commerceRequest<{ identity: string; demo: boolean }>("/coach/session");
    setSession(s); setTasks(await commerceRequest<ReviewOrder[]>("/coach/tasks"));
  }
  useEffect(() => {
    let alive = true;
    commerceRequest<ReviewCatalog>("/reviews/catalog").then(c => { if (alive) setDemo(c.simulator_available); }).catch(() => {});
    commerceRequest<{ identity: string; demo: boolean }>("/coach/session").then(async s => {
      if (alive) setSession(s);
      const t = await commerceRequest<ReviewOrder[]>("/coach/tasks");
      if (alive) setTasks(t);
    }).catch(() => {}).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);
  async function login(local: boolean) {
    setBusy(true); setError("");
    try { await commerceRequest(local ? "/coach/dev-login" : "/coach/login", local ? {} : { password }); setPassword(""); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not sign in."); }
    finally { setBusy(false); }
  }
  return <AppShell><div className="flex flex-wrap items-center justify-between gap-3"><p className="font-mono text-[10px] uppercase tracking-[.25em] text-teal">GhostRep Coach / workspace</p><Link href="/reviews" className="min-h-11 py-3 text-xs text-white/65 hover:text-teal">Athlete reviews →</Link></div><h1 className="mt-5 font-display text-4xl font-semibold">Be there for their next step.</h1><p className="mt-4 max-w-xl text-sm leading-7 text-white/60">Confirm call times, share meeting links, and review the athlete’s clips before you meet. Add personal notes when you’re ready.</p>
    {loading ? <p role="status" className="mt-8">Checking coach session…</p> : session ? <section className="mt-8"><div className="mb-6 flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-white/70">Signed in as {session.identity}{session.demo && <span className="mt-2 block text-xs text-amber">Sample coach · practice requests only</span>}</p><div className="flex gap-3"><Button variant="secondary" onClick={() => load().catch(e => setError(e.message))}>Refresh inbox</Button><Button variant="ghost" onClick={async () => { await commerceRequest("/coach/logout", {}); setSession(null); setTasks([]); }}>Sign out</Button></div></div><div className="grid gap-4 md:grid-cols-2">{tasks.length ? tasks.map(t => <OrderLink key={t.id} order={t} coach />) : <div className="col-span-full rounded-2xl border border-dashed border-white/20 p-10 text-center"><h2 className="text-xl">Your inbox is clear.</h2><p className="mt-3 text-sm text-white/55">Only server-confirmed paid reviews appear here. No draft intake grants access to a clip.</p></div>}</div></section> : <section className="mt-8 max-w-lg rounded-2xl border border-white/10 bg-[#0e1218] p-6"><h2 className="text-xl font-semibold">Coach sign-in</h2><p className="mt-3 text-xs leading-6 text-white/60">Use the private credential provisioned by the operator. Athlete sessions do not grant coach access.</p><form onSubmit={e => { e.preventDefault(); void login(false); }}><label className="mt-5 block text-sm">Coach password<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} className={fieldClass} required /></label><Button type="submit" className="mt-5 w-full" loading={busy} disabled={busy || !password}>Sign in securely</Button></form>{demo && <div className="mt-6 border-t border-white/10 pt-5"><p className="mb-4 text-xs leading-6 text-amber">Explore the sample coach inbox. This account can access practice requests only.</p><Button className="w-full" variant="secondary" disabled={busy} onClick={() => login(true)}>Open sample coach</Button></div>}</section>}
    {error && <div className="mt-5"><ActionFeedback kind="error">{error}</ActionFeedback></div>}
  </AppShell>;
}
