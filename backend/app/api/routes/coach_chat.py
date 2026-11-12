"""Authorized read-only set questions. No training writes or tool execution."""
import hashlib
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import update

from app.api.deps import current_user, get_db, meta_gateway, settings_dep
from app.config import Settings
from app.models.entities import RecordedSet, User
from app.models.commerce import CoachConversation
from app.schemas.coach_chat import CoachQuestion, CONSENT_VERSION
from app.services.coaching.chat import answer_question
from app.services.coaching.chat_context import build_context
from app.services.coaching.chat_requests import chat_requests
from app.services.meta.gateway import MetaGateway
from app.services.meta.providers import resolve_coaching_provider

router = APIRouter(tags=["coaching"])


@router.get("/coaching/{set_id}/chat/conversation")
def conversation(set_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    _owned(db, user, set_id)
    row = db.get(CoachConversation, set_id)
    return {"set_id": set_id, "turns": json.loads(row.turns_json) if row and row.user_id == user.id else []}


def save_conversation(db, user, set_id, question, reply, request_id):
    # Serialize appends after inference; this lock never spans a model request.
    db.execute(update(RecordedSet).where(RecordedSet.id == set_id, RecordedSet.user_id == user.id)
               .values(processing_status=RecordedSet.processing_status))
    row = db.get(CoachConversation, set_id)
    if row is None:
        row = CoachConversation(set_id=set_id, user_id=user.id, turns_json="[]")
        db.add(row)
    turns = json.loads(row.turns_json)
    if not any(t.get("request_id") == str(request_id) for t in turns):
        turns.append({"request_id": str(request_id), "question": question, "reply": reply})
    row.turns_json = json.dumps(turns[-6:], allow_nan=False)
    from app.models.entities import _utcnow
    row.updated_at = _utcnow()
    db.commit()


def _owned(db, user, set_id):
    rec = db.get(RecordedSet, set_id)
    if not rec or rec.user_id != user.id or not rec.session or rec.session.user_id != user.id:
        raise HTTPException(404, "Not found")
    return rec


@router.get("/coaching/{set_id}/chat/status")
def status(set_id: str, db: Session = Depends(get_db), user: User = Depends(current_user), settings: Settings = Depends(settings_dep)):
    _owned(db, user, set_id)
    return {"available": bool(settings.enable_meta_api and settings.model_api_key and resolve_coaching_provider(settings) == "meta_live"),
            "consent_version": CONSENT_VERSION, "max_question_chars": 400, "previous_question_limit": 2,
            "timeout_seconds": min(settings.coach_chat_timeout_seconds, settings.meta_request_timeout_seconds)}


@router.post("/coaching/{set_id}/chat")
async def ask(set_id: str, payload: CoachQuestion, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user), settings: Settings = Depends(settings_dep), gateway: MetaGateway = Depends(meta_gateway)):
    rec = _owned(db, user, set_id)
    selected = payload.selected_rep
    if selected is None and re.search(r"\b(this|that|selected) rep\b", payload.question, re.I):
        for previous in reversed(payload.previous_questions):
            match = re.search(r"\brep\s*#?\s*(\d{1,4})\b", previous, re.I)
            if match and any(r.rep_index == int(match[1]) for r in rec.reps):
                selected = int(match[1])
                break
    context = build_context(db, rec, payload.question, selected)
    if await request.is_disconnected():
        raise HTTPException(499, "Question closed before review started.")
    digest = hashlib.sha256(json.dumps({"set": context, "question": payload.question, "history": payload.previous_questions,
                                       "consent": payload.consent_version, "approved": payload.approve_question}, sort_keys=True, allow_nan=False).encode()).hexdigest()
    slot, cached = chat_requests.reserve(user.id, payload.request_id, digest)
    if cached is not None:
        return cached
    # SDK calls have a bounded timeout and zero SDK/application retries. Once
    # sent, disconnection cannot guarantee remote work or billing is cancelled.
    result = await run_in_threadpool(answer_question, payload, context, settings, gateway)
    save_conversation(db, user, set_id, payload.question, result, payload.request_id)
    chat_requests.finish(slot, result)
    return result
