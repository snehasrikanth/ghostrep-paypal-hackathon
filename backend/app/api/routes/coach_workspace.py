from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.deps import settings_dep
from app.api.routes.reviews import clip_payloads, provider_dep, shared_media
from app.database import get_db
from app.models.commerce import CoachSession, CoachTask, ReviewIntake, ReviewOrder
from app.schemas.commerce import AIApproval, CallConfirmation, CoachLogin, DeliveryBody, DraftBody
from app.services.commerce.assistant import coaching_draft
from app.services.commerce.auth import coach_cookie, rate_limit, require_coach, sign_in, verify_password
from app.services.commerce.evidence import shared_evidence
from app.services.commerce.orders import full_refund, now, order_out, payment_lock, reconcile_locked, selected_clips

router = APIRouter(prefix="/coach", tags=["coach workspace"])


@router.post("/login")
def login(body: CoachLogin, request: Request, response: Response, db: Session = Depends(get_db), settings=Depends(settings_dep)):
    rate_limit(request)
    if not verify_password(body.password, settings.coach_password_hash):
        raise HTTPException(401, "Invalid coach credentials.")
    return sign_in(db, response, settings)


@router.post("/dev-login")
def dev_login(response: Response, db: Session = Depends(get_db), settings=Depends(settings_dep)):
    if not settings.simulator_available:
        raise HTTPException(404, "Development coach access is disabled.")
    # This separate seeded coach identity can access simulated tasks only.
    return sign_in(db, response, settings, demo=True)


@router.get("/session")
def session(coach=Depends(require_coach)):
    return {"identity": coach.identity, "demo": coach.demo}


@router.post("/logout")
def logout(response: Response, coach=Depends(require_coach), db: Session = Depends(get_db), settings=Depends(settings_dep)):
    db.delete(coach)
    db.commit()
    response.delete_cookie(coach_cookie(settings))
    return {"ok": True}


def authorized_task(db, tid, coach):
    task = db.get(CoachTask, tid)
    order = db.get(ReviewOrder, task.order_id) if task else None
    if not order or (coach.demo and order.mode != "simulated"):
        raise HTTPException(404, "Task not found.")
    return task, order


def editable(task, order):
    if order.payment_state != "paid" or task.status in {"delivered", "canceled"}:
        raise HTTPException(409, "Only an undelivered, paid task can be edited or delivered.")


@router.get("/tasks")
def inbox(db: Session = Depends(get_db), coach=Depends(require_coach)):
    query = db.query(ReviewOrder).join(CoachTask, CoachTask.order_id == ReviewOrder.id)
    if coach.demo:
        query = query.filter(ReviewOrder.mode == "simulated")
    return [order_out(db, o, coach=True) for o in query.order_by(ReviewOrder.created_at.desc()).limit(100)]


@router.get("/tasks/{tid}")
def task(tid: str, db: Session = Depends(get_db), coach=Depends(require_coach)):
    _, order = authorized_task(db, tid, coach)
    return order_out(db, order, coach=True)


def can_view_media(task, order):
    if order.payment_state != "paid" or task.status == "canceled":
        raise HTTPException(403, "Coach sharing is paused or ended for this payment.")


@router.get("/tasks/{tid}/clips")
def clips(tid: str, db: Session = Depends(get_db), coach=Depends(require_coach)):
    task, order = authorized_task(db, tid, coach)
    can_view_media(task, order)
    return clip_payloads(db, order)


@router.get("/tasks/{tid}/clips/{rid}/media")
def media(tid: str, rid: str, db: Session = Depends(get_db), coach=Depends(require_coach)):
    task, order = authorized_task(db, tid, coach)
    can_view_media(task, order)
    return shared_media(db, order, rid)


@router.post("/tasks/{tid}/draft/generate")
def generate(tid: str, body: AIApproval, db: Session = Depends(get_db), coach=Depends(require_coach), settings=Depends(settings_dep)):
    task, order = authorized_task(db, tid, coach)
    editable(task, order)
    intake = db.get(ReviewIntake, order.intake_id)
    if body.ai_consent and not intake.ai_consented_at:
        raise HTTPException(422, "The athlete did not consent to AI processing of shared evidence. Use the local evidence draft.")
    revision = task.draft_revision
    text, source = coaching_draft(db, settings, intake,
                                 [shared_evidence(db, r) for r in selected_clips(db, intake) if r], body.ai_consent)
    with payment_lock(db, order):
        db.refresh(task)
        editable(task, order)
        if task.draft_revision != revision:
            raise HTTPException(409, "Draft changed while generation ran. Reload before replacing it.")
        task.draft, task.draft_source, task.status = text, source, "draft"
        task.draft_revision += 1
        db.commit()
    return order_out(db, order, coach=True)


@router.put("/tasks/{tid}/draft")
def save_draft(tid: str, body: DraftBody, db: Session = Depends(get_db), coach=Depends(require_coach)):
    task, order = authorized_task(db, tid, coach)
    with payment_lock(db, order):
        db.refresh(task)
        editable(task, order)
        if task.draft_revision != body.revision:
            raise HTTPException(409, "Draft revision changed. Reload before saving.")
        if not body.text.strip() and not any((getattr(body, field) or "").strip() for field in ("assessment", "ai_comparison", "next_steps")):
            raise HTTPException(422, "Write your assessment or notes before saving.")
        task.draft = body.text.strip()
        for field in ("assessment", "ai_comparison", "next_steps"):
            value = getattr(body, field)
            if value is not None:
                setattr(task, field, value.strip())
        task.draft_source = "human edited" if task.draft_source != "human" else "human"
        task.draft_revision += 1
        task.status = "draft"
        db.commit()
    return order_out(db, order, coach=True)


@router.post("/tasks/{tid}/deliver")
def deliver(tid: str, body: DeliveryBody, db: Session = Depends(get_db), coach=Depends(require_coach)):
    task, order = authorized_task(db, tid, coach)
    with payment_lock(db, order):
        db.refresh(task)
        editable(task, order)
        intake = db.get(ReviewIntake, order.intake_id)
        if intake.shared_context_json and not all((task.assessment, task.ai_comparison, task.next_steps)):
            raise HTTPException(422, "Add your independent assessment, your view of the saved suggestion, and tailored next steps before delivering notes.")
        text = task.draft
        if all((task.assessment, task.ai_comparison, task.next_steps)):
            text = (f"Instructor assessment\n{task.assessment}\n\nReview of the saved suggestion\n{task.ai_comparison}"
                    f"\n\nYour next steps\n{task.next_steps}" + (f"\n\nAdditional notes\n{task.draft}" if task.draft else ""))
        if not body.reviewed_and_approved or body.revision != task.draft_revision or len(text.strip()) < 20:
            raise HTTPException(422, "Save the current draft and explicitly approve it before delivery.")
        if "Add your response to the athlete’s question" in text:
            raise HTTPException(422, "Replace the draft prompt with your own response before approving delivery.")
        task.delivered_text, task.author, task.delivered_at = text, coach.identity, now()
        task.status = "delivered"
        db.commit()
    return order_out(db, order, coach=True)


@router.post("/tasks/{tid}/refund")
def refund(tid: str, db: Session = Depends(get_db), coach=Depends(require_coach),
           settings=Depends(settings_dep), provider=Depends(provider_dep)):
    _, order = authorized_task(db, tid, coach)
    full_refund(db, order, settings, provider)
    return order_out(db, order, coach=True)


@router.post("/tasks/{tid}/reconcile")
def reconcile(tid: str, db: Session = Depends(get_db), coach=Depends(require_coach),
              settings=Depends(settings_dep), provider=Depends(provider_dep)):
    _, order = authorized_task(db, tid, coach)
    with payment_lock(db, order):
        reconcile_locked(db, order, settings, provider)
    return order_out(db, order, coach=True)


@router.post("/tasks/{tid}/calls/{cid}/confirm")
def confirm_schedule(tid: str, cid: str, body: CallConfirmation, db: Session = Depends(get_db), coach=Depends(require_coach)):
    from app.services.commerce.scheduling import confirm_call
    _, order = authorized_task(db, tid, coach)
    with payment_lock(db, order):
        confirm_call(db, order, cid, body.starts_at, body.meeting_url)
    return order_out(db, order, coach=True)


@router.post("/tasks/{tid}/calls/{cid}/complete")
def finish_call(tid: str, cid: str, db: Session = Depends(get_db), coach=Depends(require_coach)):
    from app.services.commerce.scheduling import complete_call
    _, order = authorized_task(db, tid, coach)
    with payment_lock(db, order):
        complete_call(db, order, cid)
    return order_out(db, order, coach=True)


@router.post("/tasks/{tid}/calls/{cid}/cancel")
def cancel_schedule(tid: str, cid: str, db: Session = Depends(get_db), coach=Depends(require_coach)):
    from app.services.commerce.scheduling import cancel_call
    _, order = authorized_task(db, tid, coach)
    with payment_lock(db, order):
        cancel_call(db, order, cid)
    return order_out(db, order, coach=True)
