import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import current_user, settings_dep
from app.database import get_db
from app.models.commerce import ClipShare, CoachTask, ReviewIntake, ReviewOrder, ServicePackage
from app.models.entities import RecordedSet, User
from app.schemas.commerce import CallRequest, CheckoutBody, IntakeBody, SimulateBody
from app.services.commerce.assistant import live_available, recommend
from app.services.commerce.catalog import active_packages
from app.services.commerce.handoff import handoff_context, prior_support
from app.services.commerce.evidence import shared_evidence
from app.services.commerce.orders import (capture_order, check_order_eligibility, create_local_order, ensure_checkout,
    history, iso, now, order_out, payment_lock, reconcile_locked, selected_clips, task_once, validate_clips)
from app.services.commerce.paypal import PayPal
from app.services.recording_provenance import is_sample_set

router = APIRouter(prefix="/reviews", tags=["coach reviews"])


def provider_dep(settings=Depends(settings_dep)):
    return PayPal(settings)


def owned_order(db, oid, user):
    row = db.get(ReviewOrder, oid)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Order not found.")
    return row


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), settings=Depends(settings_dep)):
    return {"packages": active_packages(db, settings, include_additional=True),
            "merchant": settings.coach_display_name, "sandbox_configured": settings.sandbox_configured,
            "prices_approved": settings.coaching_prices_approved,
            "simulator_available": settings.simulator_available, "ai_available": live_available(settings),
            "payment_environment": "PayPal Sandbox only"}


@router.get("/recordings/{rid}/handoff-context")
def context_preview(rid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return handoff_context(db, rid, user)


@router.get("/recordings")
def recordings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(RecordedSet).filter_by(user_id=user.id, exercise_id="barbell_squat").filter(
        RecordedSet.entry_source.in_(["video", "demo"])).order_by(RecordedSet.created_at.desc()).limit(60).all()
    return [{"id": r.id, "set_index": r.set_index, "created_at": iso(r.created_at),
             "analysis_ready": bool(r.analysis and r.processing_status == "COMPLETED"),
             "processing_status": r.processing_status, "exercise_id": r.exercise_id,
             "synthetic": is_sample_set(r), "has_video": bool(r.normalized_path and Path(r.normalized_path).is_file()),
             "detected_reps": sum(rep.is_complete for rep in r.reps) if r.analysis else None,
             "logged_reps": r.completed_reps} for r in rows]


@router.post("/intakes")
def intake(body: IntakeBody, db: Session = Depends(get_db), user: User = Depends(current_user), settings=Depends(settings_dep)):
    if not body.share_with_coach:
        raise HTTPException(422, "Explicit consent to share the selected clips and evidence with the coach is required.")
    clips = validate_clips(db, user.id, body.recording_ids, body.mode, settings)
    if body.previous_order_id:
        prior_support(db, body.previous_order_id, user.id, body.mode)
    context = None
    if body.share_ai_context:
        preview = handoff_context(db, clips[0].id, user)
        if not preview["context"] or body.context_fingerprint != preview["fingerprint"]:
            raise HTTPException(409, "The saved suggestion changed. Refresh the sharing preview and review it before checkout.")
        context = preview["context"]
    elif body.context_fingerprint:
        raise HTTPException(422, "Approve sharing the displayed suggestion before including it.")
    packages = active_packages(db, settings, include_additional=bool(body.previous_order_id))
    evidence = [shared_evidence(db, r) for r in clips]
    recommendation = recommend(db, settings, body, packages, evidence)
    row = ReviewIntake(user_id=user.id, question=body.question.strip(), budget_cents=body.budget_cents, mode=body.mode,
                      ai_consented_at=now() if body.ai_consent else None, recommendation_json=json.dumps(recommendation),
                      shared_context_json=json.dumps(context) if context else None, previous_order_id=body.previous_order_id)
    db.add(row)
    db.flush()
    for position, rec in enumerate(clips):
        db.add(ClipShare(intake_id=row.id, recording_id=rec.id, position=position))
    db.commit()
    return {"id": row.id, "recommendation": recommendation, "mode": row.mode,
            "recording_ids": body.recording_ids, "question": row.question, "budget_cents": row.budget_cents,
            "shared_context": context}


@router.get("/intakes/{iid}")
def saved_intake(iid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.get(ReviewIntake, iid)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Intake not found.")
    return {"id": row.id, "question": row.question, "mode": row.mode, "recommendation": json.loads(row.recommendation_json),
            "shared_context": json.loads(row.shared_context_json) if row.shared_context_json else None}


@router.post("/orders")
def checkout(body: CheckoutBody, db: Session = Depends(get_db), user: User = Depends(current_user),
             settings=Depends(settings_dep), provider=Depends(provider_dep)):
    order = create_local_order(db, settings, user, body)
    ensure_checkout(db, order, settings, provider)
    return order_out(db, order)


@router.get("/orders")
def orders(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [order_out(db, o) for o in db.query(ReviewOrder).filter_by(user_id=user.id).order_by(ReviewOrder.created_at.desc()).limit(100)]


@router.get("/orders/{oid}")
def receipt(oid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return order_out(db, owned_order(db, oid, user))


@router.post("/orders/{oid}/capture")
def capture(oid: str, db: Session = Depends(get_db), user: User = Depends(current_user),
            settings=Depends(settings_dep), provider=Depends(provider_dep)):
    order = owned_order(db, oid, user)
    capture_order(db, order, settings, provider)
    return order_out(db, order)


@router.post("/orders/{oid}/reconcile")
def reconcile(oid: str, db: Session = Depends(get_db), user: User = Depends(current_user),
              settings=Depends(settings_dep), provider=Depends(provider_dep)):
    order = owned_order(db, oid, user)
    if not order.provider_order_id:
        ensure_checkout(db, order, settings, provider)
    else:
        with payment_lock(db, order):
            reconcile_locked(db, order, settings, provider)
    return order_out(db, order)


@router.post("/orders/{oid}/cancel")
def cancel(oid: str, db: Session = Depends(get_db), user: User = Depends(current_user),
           settings=Depends(settings_dep), provider=Depends(provider_dep)):
    order = owned_order(db, oid, user)
    with payment_lock(db, order):
        if order.mode == "sandbox" and order.provider_order_id:
            reconcile_locked(db, order, settings, provider)
        if order.payment_state in {"paid", "refunded", "refund_pending", "capture_pending"}:
            raise HTTPException(409, "A captured or pending payment cannot be canceled here. Contact the coach for a refund.")
        history(db, order, "canceled", "Buyer canceled checkout. No coach task released. A fresh intake is required to purchase again.")
        db.commit()
    return order_out(db, order)


@router.post("/orders/{oid}/simulate")
def simulate(oid: str, body: SimulateBody, db: Session = Depends(get_db), user: User = Depends(current_user), settings=Depends(settings_dep)):
    order = owned_order(db, oid, user)
    if order.mode != "simulated" or not settings.simulator_available:
        raise HTTPException(404, "Simulator unavailable.")
    with payment_lock(db, order):
        if order.payment_state in {"paid", "refunded", "refund_pending"}:
            return order_out(db, order)
        if order.payment_state == "canceled":
            raise HTTPException(409, "Canceled orders cannot be simulated. Create a new intake.")
        check_order_eligibility(db, order, settings)
        state = {"completed": "paid", "pending": "capture_pending", "failed": "failed"}[body.result]
        if state == "paid":
            order.capture_id = f"SIM-CAPTURE-{order.id}"
            task_once(db, order, settings)
        history(db, order, state, f"SIMULATED {body.result}. No PayPal transaction occurred.")
        db.commit()
    return order_out(db, order)


def clip_payloads(db, order):
    from app.api.routes.analysis import get_overlay
    intake = db.get(ReviewIntake, order.intake_id)
    athlete = db.get(User, order.user_id)
    result = []
    for rec in selected_clips(db, intake):
        if not rec:
            continue
        result.append({**shared_evidence(db, rec),
                       "has_video": bool(rec.normalized_path and Path(rec.normalized_path).is_file()),
                       "overlay": get_overlay(rec.id, db, athlete) if rec.analysis_requested and rec.analysis else None})
    return result


@router.get("/orders/{oid}/clips")
def clips(oid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return clip_payloads(db, owned_order(db, oid, user))


def shared_media(db, order, rid):
    share = db.query(ClipShare).filter_by(intake_id=order.intake_id, recording_id=rid).one_or_none()
    rec = db.get(RecordedSet, rid) if share else None
    if not rec or rec.user_id != order.user_id or not rec.normalized_path or not Path(rec.normalized_path).is_file():
        raise HTTPException(404, "Shared clip unavailable or deleted.")
    return FileResponse(rec.normalized_path, media_type="video/mp4", headers={"Cache-Control": "private, no-store"})


@router.get("/orders/{oid}/clips/{rid}/media")
def media(oid: str, rid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return shared_media(db, owned_order(db, oid, user), rid)


@router.post("/orders/{oid}/calls")
def request_schedule(oid: str, body: CallRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.services.commerce.scheduling import request_calls
    order = owned_order(db, oid, user)
    with payment_lock(db, order):
        request_calls(db, order, body.starts_at, body.timezone)
    return order_out(db, order)


@router.post("/orders/{oid}/calls/{cid}/request")
def request_call_change(oid: str, cid: str, body: CallRequest, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.services.commerce.scheduling import request_call_change
    order = owned_order(db, oid, user)
    with payment_lock(db, order):
        request_call_change(db, order, cid, body.starts_at, body.timezone)
    return order_out(db, order)


@router.post("/orders/{oid}/calls/{cid}/cancel")
def cancel_call(oid: str, cid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.services.commerce.scheduling import cancel_call
    order = owned_order(db, oid, user)
    with payment_lock(db, order):
        cancel_call(db, order, cid)
    return order_out(db, order)
