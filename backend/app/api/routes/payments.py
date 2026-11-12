"""Agentic fitness-commerce payment surface. Prices and capture verification stay server-side."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user, settings_dep
from app.database import get_db
from app.models.commerce import ClipShare, ReviewIntake, ReviewOrder
from app.models.entities import User
from app.schemas.commerce import AgenticIntakeBody, PaymentCheckoutBody, SimulateBody, PlanReviewBody
from app.services.commerce.assistant import live_available, recommend
from app.services.commerce.catalog import active_packages
from app.services.commerce.evidence import shared_evidence
from app.services.commerce.orders import (capture_order, create_local_order, ensure_checkout, history, iso, now,
    order_out, payment_lock, reconcile_locked, validate_clips)
from app.services.commerce.paypal import PayPal, ProviderError
from app.services.recording_provenance import is_sample_set

router = APIRouter(prefix="/api/payments", tags=["agentic payments"])


def provider_dep(settings=Depends(settings_dep)):
    return PayPal(settings)


def owned_order(db, oid, user):
    row = db.get(ReviewOrder, oid)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "Order not found.")
    return row


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), settings=Depends(settings_dep)):
    packages = active_packages(db, settings, family="agentic")
    return {
        "packages": packages,
        "merchant": settings.coach_display_name,
        "sandbox_configured": settings.sandbox_configured,
        "simulator_available": settings.simulator_available,
        "ai_available": live_available(settings),
        "payment_environment": "PayPal Sandbox only",
        "notice": "Demo prices and demo services. Automated feedback and live coach review are separate services.",
    }


@router.get("/config")
def payment_config(settings=Depends(settings_dep), provider=Depends(provider_dep)):
    """Public client ID + short-lived browser token. Never returns the client secret."""
    payload = {
        "sandbox": True,
        "currency": "USD",
        "client_id": settings.paypal_client_id if settings.sandbox_configured else None,
        "client_token": None,
        "sdk_url": "https://www.sandbox.paypal.com/web-sdk/v6/core",
        "configured": settings.sandbox_configured,
    }
    if not settings.sandbox_configured:
        return payload
    return payload


@router.post("/recommendations")
def create_recommendation(body: AgenticIntakeBody, db: Session = Depends(get_db),
                          user: User = Depends(current_user), settings=Depends(settings_dep)):
    if not body.share_with_coach:
        raise HTTPException(422, "Explicit consent to share the selected clips and evidence is required before a recommendation.")
    clips = validate_clips(db, user.id, body.recording_ids, body.mode, settings)
    packages = active_packages(db, settings, family="agentic")
    evidence = [shared_evidence(db, r) for r in clips]
    recommendation = recommend(db, settings, body, packages, evidence)
    row = ReviewIntake(user_id=user.id, question=body.question.strip(), budget_cents=body.budget_cents, mode=body.mode,
                       ai_consented_at=now() if body.ai_consent else None,
                       recommendation_json=json.dumps(recommendation))
    db.add(row)
    db.flush()
    for position, rec in enumerate(clips):
        db.add(ClipShare(intake_id=row.id, recording_id=rec.id, position=position))
    db.commit()
    return {
        "id": row.id,
        "recommendation": recommendation,
        "mode": row.mode,
        "recording_ids": body.recording_ids,
        "question": row.question,
        "budget_cents": row.budget_cents,
        "catalog": packages,
        "requires_approval": True,
        "notice": "Checkout starts only after you explicitly approve a service. Prices come from the server catalog.",
    }


@router.get("/plan-reviews/{plan_id}")
def plan_review_preview(plan_id: str, db: Session = Depends(get_db), user: User = Depends(current_user), settings=Depends(settings_dep)):
    from app.services.commerce.plan_review import snapshot
    return snapshot(db, user.id, plan_id, settings)


@router.post("/plan-reviews")
def create_plan_review(body: PlanReviewBody, db: Session = Depends(get_db),
                       user: User = Depends(current_user), settings=Depends(settings_dep)):
    from app.services.commerce.plan_review import snapshot
    from app.services.commerce.scheduling import future, zone
    if not body.share_with_coach:
        raise HTTPException(422, "Approve sharing your plan, restrictions and preferences with the coach first.")
    future(body.preferences.preferred_at)
    zone(body.preferences.timezone)
    saved = snapshot(db, user.id, body.plan_id, settings)
    if saved["fingerprint"] != body.context_fingerprint:
        raise HTTPException(409, "Your plan or restrictions changed. Reload this page and review the updated sharing scope.")
    package = next((p for p in active_packages(db, settings, family="agentic")
                    if p["id"] == "personal-coaching-session"), None)
    if not package:
        raise HTTPException(422, "Personal coaching is unavailable.")
    saved["preferences"] = body.preferences.model_dump(mode="json")
    saved["availability_status"] = "requested"
    recommendation = {"outcome": "recommend", "package_id": package["id"], "source": "plan_review",
                      "source_label": "Your plan review request", "explanation": "Live coach review of the shared plan and restrictions.",
                      "limits": "Coach matching and appointment time require confirmation. Sandbox demo service."}
    row = ReviewIntake(user_id=user.id, question=body.question.strip(), mode=saved["mode"],
                       recommendation_json=json.dumps(recommendation), shared_context_json=json.dumps(saved))
    db.add(row); db.commit()
    return {"id": row.id, "plan_review": saved, "package": package, "mode": row.mode}


@router.post("/orders")
def create_order(body: PaymentCheckoutBody, db: Session = Depends(get_db), user: User = Depends(current_user),
                 settings=Depends(settings_dep), provider=Depends(provider_dep)):
    if not body.approved:
        raise HTTPException(422, "Explicit approval is required before PayPal checkout.")
    package = next((p for p in active_packages(db, settings, family="agentic") if p["id"] == body.package_id), None)
    # Allow instructor packages through the same verified payment path when explicitly selected.
    if package is None:
        package = next((p for p in active_packages(db, settings, include_additional=True) if p["id"] == body.package_id), None)
    if package is None:
        raise HTTPException(422, "Package is unavailable.")
    order = create_local_order(db, settings, user, body)
    ensure_checkout(db, order, settings, provider)
    return order_out(db, order)


@router.get("/orders")
def purchase_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.query(ReviewOrder).filter_by(user_id=user.id).order_by(ReviewOrder.created_at.desc()).limit(100).all()
    return [order_out(db, o) for o in rows]


@router.get("/orders/{oid}")
def order_status(oid: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
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
            raise HTTPException(409, "A captured or pending payment cannot be canceled here.")
        history(db, order, "canceled", "Buyer canceled checkout. No fulfillment released.")
        db.commit()
    return order_out(db, order)


@router.post("/orders/{oid}/simulate")
def simulate(oid: str, body: SimulateBody, db: Session = Depends(get_db), user: User = Depends(current_user),
             settings=Depends(settings_dep)):
    from app.services.commerce.orders import check_order_eligibility, task_once
    order = owned_order(db, oid, user)
    if order.mode != "simulated" or not settings.simulator_available:
        raise HTTPException(404, "Simulator unavailable.")
    with payment_lock(db, order):
        if order.payment_state in {"paid", "refunded", "refund_pending"}:
            return order_out(db, order)
        if order.payment_state == "canceled":
            raise HTTPException(409, "Canceled orders cannot be simulated. Create a new recommendation.")
        check_order_eligibility(db, order, settings)
        state = {"completed": "paid", "pending": "capture_pending", "failed": "failed"}[body.result]
        if state == "paid":
            order.capture_id = f"SIM-CAPTURE-{order.id}"
            task_once(db, order, settings)
        history(db, order, state, f"SIMULATED {body.result}. No PayPal transaction occurred.")
        db.commit()
    return order_out(db, order)


@router.get("/recordings")
def recordings(db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.models.entities import RecordedSet
    rows = db.query(RecordedSet).filter_by(user_id=user.id, exercise_id="barbell_squat").filter(
        RecordedSet.entry_source.in_(["video", "demo"])).order_by(RecordedSet.created_at.desc()).limit(60).all()
    return [{"id": r.id, "set_index": r.set_index, "created_at": iso(r.created_at),
             "analysis_ready": bool(r.analysis and r.processing_status == "COMPLETED"),
             "processing_status": r.processing_status, "exercise_id": r.exercise_id,
             "synthetic": is_sample_set(r), "has_video": bool(r.normalized_path and Path(r.normalized_path).is_file()),
             "detected_reps": sum(rep.is_complete for rep in r.reps) if r.analysis else None,
             "logged_reps": r.completed_reps} for r in rows]


@router.get("/demo-guide")
def demo_guide(db: Session = Depends(get_db), user: User = Depends(current_user), settings=Depends(settings_dep)):
    from app.models.entities import WorkoutPlan, RecordedSet
    from app.services.demo.identity import DEMO_USER_ID
    if not settings.simulator_available or user.id != DEMO_USER_ID:
        raise HTTPException(404, "Open the development demo athlete first.")
    plan = db.query(WorkoutPlan).filter_by(user_id=user.id).order_by(WorkoutPlan.created_at.desc()).first()
    recording = db.query(RecordedSet).filter_by(user_id=user.id, entry_source="demo", processing_status="COMPLETED").order_by(RecordedSet.created_at.desc()).first()
    return {"plan_id": plan.id if plan else None, "recording_id": recording.id if recording else None,
            "simulated": True, "notice": "Synthetic journal and simulated payments. No PayPal transaction or paid inference."}
