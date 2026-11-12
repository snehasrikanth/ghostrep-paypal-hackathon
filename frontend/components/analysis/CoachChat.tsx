"use client";

import { useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { MessageCircle, Send, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { buttonClass } from "@/lib/buttonStyles";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CoachOffer } from "@/components/reviews/CoachOffer";
import { ExerciseDemo } from "@/components/workout/ExerciseDemo";
import { COACH_QUESTIONS, canExploreHumanCoaching, coachActions, coachReplayHref, questionHistory, safeCoachHref, validCoachQuestion, type CoachStatus, type CoachTurn } from "@/lib/coachChat";

export function CoachChat({setId, exerciseId, selectedRep, onReplay, defaultOpen=false}: {
  setId:string;exerciseId:string;selectedRep:number|null;onReplay:(seconds:number,repId:number)=>void;defaultOpen?:boolean;
}) {
  const id=useId(), trigger=useRef<HTMLButtonElement>(null), input=useRef<HTMLTextAreaElement>(null);
  const pending=useRef<AbortController|null>(null), mounted=useRef(true), openingScroll=useRef(0);
  const conversationRef=useRef<HTMLDivElement>(null);
  const [open,setOpen]=useState(defaultOpen),[status,setStatus]=useState<CoachStatus|null>(null),[statusError,setStatusError]=useState(false);
  const [historyReady,setHistoryReady]=useState(false);
  const [consent,setConsent]=useState(false),[draft,setDraft]=useState(""),[turns,setTurns]=useState<CoachTurn[]>([]);
  const [busy,setBusy]=useState(false),[activeQuestion,setActiveQuestion]=useState(""),[error,setError]=useState<string|null>(null);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;pending.current?.abort();};},[]);
  useEffect(()=>{
    let alive=true;
    api.coachConversation(setId).then(saved=>{if(alive&&saved.set_id===setId)setTurns(saved.turns);})
      .catch(()=>{if(alive)setError("Your earlier conversation could not be loaded. You can still ask about this set.");})
      .finally(()=>{if(alive)setHistoryReady(true);});
    if(defaultOpen) void api.coachChatStatus(setId).then(s=>{if(alive)setStatus(s);}).catch(()=>{if(alive)setStatusError(true);});
    return()=>{alive=false;};
  },[setId,defaultOpen]);
  useEffect(()=>{
    if(!open)return;
    const conversation=conversationRef.current;
    if(conversation) conversation.scrollTo({top:conversation.scrollHeight,behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"instant":"smooth"});
  },[busy,turns,open]);
  async function loadStatus() {
    setStatusError(false);
    try {const s=await api.coachChatStatus(setId);if(mounted.current)setStatus(s);}
    catch {if(mounted.current)setStatusError(true);}
  }
  function toggle() {
    if(open){setOpen(false);trigger.current?.focus({preventScroll:true});requestAnimationFrame(()=>window.scrollTo({top:openingScroll.current,behavior:"instant"}));}
    else {openingScroll.current=window.scrollY;setOpen(true);if(!status)void loadStatus();}
  }
  async function ask(question:string) {
    // Ref blocks the second click before React has rendered the busy state.
    if(pending.current || !historyReady || !validCoachQuestion(question))return;
    const controller=new AbortController();pending.current=controller;
    setBusy(true);setError(null);setActiveQuestion(question.trim());setDraft(question);
    const timeout=setTimeout(()=>controller.abort("timeout"),(Math.min(90,Math.max(1,status?.timeout_seconds??30))+5)*1000);
    try {
      const reply=await api.askCoach(setId,{
        request_id:crypto.randomUUID(),question:question.trim(),previous_questions:questionHistory(turns),selected_rep:selectedRep,
        approve_question:Boolean(status?.available&&consent),consent_version:status?.available&&consent?status.consent_version:null,
      },controller.signal);
      if(mounted.current && !controller.signal.aborted && reply.set_id===setId){setTurns(t=>[...t,{question:question.trim(),reply}].slice(-6));setDraft("");}
    } catch (err) {
      if(mounted.current)setError(controller.signal.aborted?"Answer stopped on this page. A request already sent may still finish and be billed. Nothing will retry automatically.":err instanceof ApiError&&[409,429].includes(err.status)?err.message:"Your question could not be answered. Your set is unchanged. Try again yourself or use the saved evidence and recommendation.");
    } finally {
      clearTimeout(timeout);if(pending.current===controller)pending.current=null;
      if(mounted.current){setBusy(false);setActiveQuestion("");}
    }
  }
  useEffect(() => {
    const openFromLink = () => {
      if (window.location.hash === "#ask-coach") { setOpen(true); void loadStatus(); }
    };
    const frame = requestAnimationFrame(openFromLink);
    window.addEventListener("hashchange", openFromLink);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("hashchange", openFromLink); };
    // Opening the coach only checks availability; it never sends a question.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setId]);
  function navigateTo(id:string) {
    const target=document.getElementById(id);
    if(target){target.scrollIntoView({block:"start",behavior:"smooth"});target.focus({preventScroll:true});}
    else window.location.assign(`/analysis/${setId}#${id}`); // eslint-disable-line @next/next/no-location-assign-relative-destination
  }
  return <Card id="ask-coach" className="scroll-mt-24 min-w-0 border-white/10 p-4 [overflow-wrap:anywhere] sm:p-5">
    <button ref={trigger} type="button" className={buttonClass("secondary","w-full justify-between")} aria-expanded={open} aria-controls={`${id}-panel`} onClick={toggle}>
      <span className="flex items-center gap-2"><MessageCircle size={17} aria-hidden="true"/>Ask my coach</span><span aria-hidden="true">{open?"−":"+"}</span>
    </button>
    {!open && <CoachOffer recordingId={setId} />}
    <div id={`${id}-panel`} hidden={!open} role="region" aria-label="Ask my coach" className="mt-4" onKeyDown={e=>{if(e.key==="Escape"){e.stopPropagation();toggle();}}}>
      <p className="text-sm leading-6 text-white/80">AI coach · ask about this set’s saved evidence.</p>
      <p className="mt-1 text-xs leading-5 text-white/60">Your conversation is saved privately with this recording. Follow-ups use your last two questions.</p>
      <details className="mt-2 text-xs leading-5 text-white/65"><summary className="flex min-h-11 cursor-pointer items-center text-teal">What this coach can tell you</summary><p>Answers describe saved measurements and recommendations. They do not establish safe or correct technique, fatigue, or injury risk. Your reference is an observed rep, not ideal form. Correcting logged reps does not create measured repetitions.</p></details>
      {status?.available && <div className="mt-3 rounded-xl border border-white/10 p-3 text-xs leading-5 text-white/80">
        <label className="flex min-h-11 cursor-pointer items-start gap-2"><input type="checkbox" className="mt-1 h-5 w-5 shrink-0 accent-teal" checked={consent} onChange={e=>setConsent(e.target.checked)} disabled={busy}/><span>Share my submitted questions and this set’s evidence for personalized answers.</span></label>
        <details><summary className="flex min-h-11 cursor-pointer items-center text-teal">What is shared and how requests work</summary><p>Your question, up to two previous questions on this set, and structured training evidence go to Meta’s coaching service (Muse Spark). No video, unrelated profile or training history is sent. Each submission permits at most one paid request under the app’s configured limits; no automatic retries. Without this choice, you get a basic saved-evidence summary. Closing this panel does not cancel an already sent request.</p></details>
      </div>}
      {status && !status.available && <p className="mt-3 text-xs leading-5 text-white/70">Personalized answers are unavailable. Basic saved-evidence summaries work without sharing questions with a coaching service.</p>}
      {statusError && <div role="status" className="mt-3 text-xs leading-5 text-amber"><p>Could not check coaching availability. You can still ask for a basic saved-evidence summary.</p><Button variant="ghost" onClick={()=>void loadStatus()}>Retry availability</Button></div>}
      <details className="mt-3" open={turns.length === 0}>
        <summary className="min-h-11 cursor-pointer py-3 text-xs text-teal">{turns.length ? "More starter questions" : "Start with a question"}</summary>
        <div className="flex flex-wrap gap-2" aria-label="Starter questions">
          {COACH_QUESTIONS.map(q=><button key={q} disabled={busy||!historyReady} onClick={()=>void ask(q)} className="min-h-11 max-w-full rounded-xl border border-teal/25 bg-teal/5 px-3 py-2 text-left text-xs leading-5 text-teal disabled:opacity-50">{q}</button>)}
        </div>
      </details>
      <div ref={conversationRef} tabIndex={0} className="mt-4 max-h-[min(32rem,60dvh)] space-y-4 overflow-y-auto overscroll-contain rounded-xl focus-visible:outline-2 focus-visible:outline-teal" role="log" aria-label="Coach conversation" aria-live="polite" aria-relevant="additions">
        {turns.map((turn,i)=><div key={i} className="space-y-2 border-t border-white/10 pt-3">
          <p className="text-sm font-medium text-white/90"><span className="sr-only">You asked: </span>{turn.question}</p>
          <div className="rounded-xl bg-black/25 p-4">
            {turn.reply.headline&&<p className="text-base font-semibold leading-6 text-white">{turn.reply.headline}</p>}
            <p className="mt-2 max-w-3xl whitespace-pre-wrap text-sm leading-6 text-white/90">{turn.reply.answer}</p>
            {turn.reply.uncertainty&&<p className="mt-2 text-xs leading-5 text-white/65">{turn.reply.uncertainty}</p>}
            {turn.reply.notice&&turn.reply.notice!=="No question was sent to the coaching service."&&<p className="mt-2 text-xs leading-5 text-amber">{turn.reply.notice}</p>}
            <div className="mt-3 flex min-w-0 flex-wrap gap-2">
              {coachActions(turn.reply).map((action, index) => {
                const prominent = action.emphasis === "primary" || (action.emphasis !== "secondary" && index === 0);
                const className = buttonClass(prominent ? "primary" : "ghost", "max-w-full whitespace-normal text-left");
                if (action.kind === "replay" && action.set_id && action.rep_id != null && action.seconds != null) {
                  const href = coachReplayHref({set_id:action.set_id, rep_id:action.rep_id, seconds:action.seconds});
                  if (!href) return null;
                  return action.set_id === setId
                    ? <button key={`${action.kind}-${index}`} type="button" className={className} onClick={() => {onReplay(action.seconds!, action.rep_id!); navigateTo("set-replay");}}>{action.label}</button>
                    : <Link key={`${action.kind}-${index}`} href={href} className={className}>{action.label}</Link>;
                }
                if (action.kind === "review_recommendation") return <button key={`${action.kind}-${index}`} type="button" className={className} onClick={() => navigateTo("set-recommendation")}>{action.label}</button>;
                if (action.kind === "view_comparison") return <button key={`${action.kind}-${index}`} type="button" className={className} onClick={() => navigateTo("set-comparison")}>{action.label}</button>;
                if (action.kind === "watch_demo") return <ExerciseDemo key={`${action.kind}-${index}`} exerciseId={exerciseId} />;
                const workout = action.kind === "workout" ? safeCoachHref(action.href) : null;
                return workout ? <Link key={`${action.kind}-${index}`} href={workout} className={className}>{action.label}</Link> : null;
              })}
            </div>
            <p className="mt-2 text-xs text-white/55">{turn.reply.source==="basic"?(turn.reply.notice==="No question was sent to the coaching service."?"Saved-evidence summary · no question sent":"Basic saved-evidence summary"):turn.reply.basis}</p>
          </div>
        </div>)}
      {busy&&<div role="status" className="mt-4 rounded-xl border border-teal/20 p-3 text-sm leading-6"><p className="text-white/70">{activeQuestion}</p><p className="mt-1 text-teal">{status?.available&&consent?"Your AI coach is reviewing your question…":"Reviewing your saved evidence…"}</p><Button variant="ghost" onClick={()=>pending.current?.abort()}>Stop waiting</Button></div>}
      </div>

      {!busy && (turns.length === 0 || canExploreHumanCoaching(turns)) && <CoachOffer recordingId={setId} />}
      {error&&<p role="alert" className="mt-3 text-sm leading-6 text-amber">{error}</p>}
      <form className="mt-4" onSubmit={e=>{e.preventDefault();void ask(draft);}}>
        <label htmlFor={`${id}-question`} className="text-sm font-medium">Your question</label>
        <textarea ref={input} id={`${id}-question`} maxLength={400} rows={3} value={draft} onChange={e=>setDraft(e.target.value)} placeholder="Ask about this set…" disabled={busy} aria-describedby={`${id}-limit`} className="mt-2 w-full resize-y rounded-xl border border-white/20 bg-black/30 p-3 text-base leading-6 outline-none focus-visible:border-teal focus-visible:ring-2 focus-visible:ring-teal/40 disabled:opacity-60"/>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2"><p id={`${id}-limit`} className="text-xs text-white/60">{draft.length}/400 characters</p><Button type="submit" disabled={busy||!historyReady||!validCoachQuestion(draft)}><Send size={15} aria-hidden="true"/>{status?.available&&consent?"Ask my coach":"Ask about saved evidence"}</Button></div>
      </form>
      <Button variant="ghost" className="mt-3" onClick={toggle}><X size={15} aria-hidden="true"/>Close coach questions</Button>
    </div>
  </Card>;
}
