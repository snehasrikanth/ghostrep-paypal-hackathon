"""Private, immutable sharing of the exact saved suggestion the athlete reviewed."""
import hashlib
import json

from fastapi import HTTPException

from app.api.serialize import coaching_out
from app.models.commerce import CoachConversation, CoachingCall, CoachTask, ReviewOrder
from app.models.entities import RecordedSet


def handoff_context(db, recording_id, user):
    rec = db.get(RecordedSet, recording_id)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404, "Recording not found.")
    suggestion = None
    if rec.coaching:
        saved = coaching_out(rec.coaching, rec=rec, session=rec.session)
        keys = ("id", "revision", "source", "source_label", "summary", "reason", "primary_cue", "suggested_action",
                "suggested_reps", "suggested_rest_seconds", "suggested_load_kg", "actionable", "user_decision")
        suggestion = {key: saved.get(key) for key in keys}
    latest = None
    conversation = db.get(CoachConversation, rec.id)
    if conversation and conversation.user_id == user.id:
        turns = json.loads(conversation.turns_json)
        if turns:
            turn = turns[-1]
            reply = turn["reply"]
            latest = {"question": turn["question"], **{key: reply.get(key) for key in
                      ("headline", "answer", "uncertainty", "source", "notice", "basis")},
                      "evidence": [e for e in reply.get("evidence", []) if e.get("set_id") == rec.id][:4]}
    context = {"recording_id": rec.id, "suggestion": suggestion, "latest_answer": latest} if suggestion or latest else None
    digest = hashlib.sha256(json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest() if context else None
    return {"context": context, "fingerprint": digest}


def followup_available(db, order):
    if order.payment_state != "paid" or json.loads(order.package_json).get("kind") == "ai_report":
        return False
    task = db.query(CoachTask).filter_by(order_id=order.id).one_or_none()
    return bool((task and task.status == "delivered") or db.query(CoachingCall).filter_by(order_id=order.id, status="completed").first())


def prior_support(db, order_id, user_id, mode):
    order = db.get(ReviewOrder, order_id) if order_id else None
    if not order or order.user_id != user_id or order.mode != mode:
        raise HTTPException(404, "Previous coaching purchase not found.")
    if not followup_available(db, order):
        raise HTTPException(409, "Additional support is available after a completed call or delivered instructor notes.")
    return order
