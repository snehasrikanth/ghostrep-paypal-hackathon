"""Prices and transitions live here, never in model output or browser amounts."""
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from app.models.commerce import ClipShare, CoachTask, PaymentHistory, ReviewIntake, ReviewOrder, ReviewRefund, ServicePackage
from app.models.entities import RecordedSet
from app.services.commerce.catalog import configured_package, matches_clips
from app.services.commerce.paypal import ProviderError, approval_link, cents
from app.services.demo.identity import DEMO_USER_ID
from app.services.recording_provenance import is_sample_set


def now():
    return datetime.now(timezone.utc)


def iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def shares(db, intake_id):
    return db.query(ClipShare).filter_by(intake_id=intake_id).order_by(ClipShare.position, ClipShare.id).all()


def selected_clips(db, intake):
    return [db.get(RecordedSet, s.recording_id) for s in shares(db, intake.id)]


def validate_clips(db, user_id, recording_ids, mode, settings):
    if len(set(recording_ids)) != len(recording_ids):
        raise HTTPException(422, "Choose distinct recordings.")
    if mode == "simulated" and (not settings.simulator_available or user_id != DEMO_USER_ID):
        raise HTTPException(403, "Simulation is restricted to the development demo athlete.")
    clips = []
    for rid in recording_ids:
        rec = db.get(RecordedSet, rid)
        if not rec or rec.user_id != user_id:
            raise HTTPException(404, "Recording not found.")
        if rec.exercise_id != "barbell_squat" or rec.processing_status not in {"SAVED", "COMPLETED"}:
            raise HTTPException(422, "Select saved barbell squat recordings.")
        if mode == "sandbox" and (is_sample_set(rec) or not rec.normalized_path):
            raise HTTPException(422, "Sandbox checkout requires your own saved clip, not a synthetic fixture.")
        if mode == "sandbox":
            from pathlib import Path
            if not Path(rec.normalized_path).is_file():
                raise HTTPException(422, "This clip is no longer available. Select another recording.")
        if mode == "simulated" and not is_sample_set(rec):
            raise HTTPException(422, "Simulation accepts only synthetic demo recordings.")
        clips.append(rec)
    if not 1 <= len(clips) <= 2:
        raise HTTPException(422, "Select one or two clips.")
    return clips


def check_order_eligibility(db, order, settings):
    intake = db.get(ReviewIntake, order.intake_id)
    if not intake or not intake.share_consented_at or intake.user_id != order.user_id:
        raise HTTPException(409, "Sharing consent could not be verified.")
    from app.services.commerce.plan_review import context, validate
    if context(intake):
        validate(db, intake, json.loads(order.package_json), settings)
        return intake
    clips = validate_clips(db, order.user_id, [s.recording_id for s in shares(db, intake.id)], order.mode, settings)
    if not matches_clips(json.loads(order.package_json), len(clips)):
        raise HTTPException(409, "Purchased clip scope could not be verified.")
    return intake


def history(db, order, state, detail):
    if order.payment_state == state:
        return
    order.payment_state = state
    db.add(PaymentHistory(order_id=order.id, state=state, detail=detail))


def create_local_order(db, settings, user, body):
    existing = db.query(ReviewOrder).filter_by(user_id=user.id, checkout_key=body.checkout_key).one_or_none()
    if existing:
        if existing.intake_id != body.intake_id or json.loads(existing.package_json)["id"] != body.package_id:
            raise HTTPException(409, "Checkout key belongs to a different request.")
        return existing
    intake = db.get(ReviewIntake, body.intake_id)
    if not intake or intake.user_id != user.id:
        raise HTTPException(404, "Intake not found.")
    existing = db.query(ReviewOrder).filter_by(intake_id=intake.id).one_or_none()
    if existing:
        if json.loads(existing.package_json)["id"] != body.package_id:
            raise HTTPException(409, "This intake already has an order. Create a new intake to change package.")
        return existing
    package = db.get(ServicePackage, body.package_id)
    offer = configured_package(package, settings) if package else None
    if not offer or not offer["active"] or offer["currency"] != "USD" or offer["price_cents"] <= 0:
        raise HTTPException(422, "Package is unavailable.")
    if package.id == "additional-session":
        from app.services.commerce.handoff import prior_support
        prior_support(db, intake.previous_order_id, user.id, intake.mode)
    from app.services.commerce.plan_review import context, validate
    if context(intake):
        validate(db, intake, offer, settings)
        if shares(db, intake.id):
            raise HTTPException(422, "Plan reviews cannot include recordings.")
    else:
        validate_clips(db, user.id, [s.recording_id for s in shares(db, intake.id)], intake.mode, settings)
        if not matches_clips(offer, len(shares(db, intake.id))):
            raise HTTPException(422, "Package does not match the consented clip count.")
    if not intake.share_consented_at:
        raise HTTPException(422, "Sharing consent is required.")
    if intake.budget_cents is not None and offer["price_cents"] > intake.budget_cents:
        raise HTTPException(422, "Package exceeds your budget.")
    if intake.mode == "sandbox" and not settings.sandbox_configured:
        raise HTTPException(503, "Sandbox checkout is being set up. Your feedback is still available; please try booking later.")
    order = ReviewOrder(user_id=user.id, intake_id=intake.id, checkout_key=body.checkout_key,
                        mode=intake.mode, package_json=json.dumps(offer), amount_cents=offer["price_cents"],
                        currency="USD", merchant_id=settings.paypal_merchant_id if intake.mode == "sandbox" else "SIMULATED")
    db.add(order)
    try:
        db.flush()
        db.add(PaymentHistory(order_id=order.id, state="created", detail="Package and sharing scope saved before payment."))
        db.commit()
    except IntegrityError:
        db.rollback()
        order = db.query(ReviewOrder).filter_by(intake_id=intake.id).one()
        if json.loads(order.package_json)["id"] != body.package_id:
            raise HTTPException(409, "Another checkout was created for this intake.")
    return order


@contextmanager
def payment_lock(db, order):
    """Persisted CAS lease serializes workers, callbacks and webhook mutations.

    A crash leaves a bounded lease. The next action reconciles using stable keys.
    Provider mutations start only after their request IDs and attempt times commit.
    """
    stamp = now()
    lease = stamp + timedelta(seconds=300)
    result = db.execute(update(ReviewOrder).where(ReviewOrder.id == order.id,
                       or_(ReviewOrder.lock_until.is_(None), ReviewOrder.lock_until < stamp)).values(lock_until=lease).execution_options(synchronize_session=False))
    db.commit()
    if result.rowcount != 1:
        raise HTTPException(409, "Payment operation in progress. Refresh shortly, then reconcile.")
    db.refresh(order)
    try:
        yield
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(update(ReviewOrder).where(ReviewOrder.id == order.id, ReviewOrder.lock_until == lease).values(lock_until=None).execution_options(synchronize_session=False))
        db.commit()


def retry_window(started):
    # Conservative window; never repeat uncertain POSTs after provider retention may expire.
    if started and now() - started.replace(tzinfo=timezone.utc) > timedelta(hours=5):
        raise HTTPException(409, "This operation needs merchant reconciliation in the Sandbox dashboard; automatic retry is disabled after five hours.")


def ensure_checkout(db, order, settings, provider):
    with payment_lock(db, order):
        if order.payment_state not in {"created", "uncertain", "checkout_ready"}:
            return
        if order.provider_order_id:
            reconcile_locked(db, order, settings, provider)
            return
        if order.mode == "simulated":
            order.provider_order_id = f"SIM-{order.id}"
            history(db, order, "checkout_ready", "SIMULATED checkout · no PayPal request or money movement.")
            db.commit()
            return
        retry_window(order.create_started_at)
        order.create_started_at = order.create_started_at or now()
        db.commit()
        try:
            result = provider.create(order)
            pid = result.get("id")
            if not isinstance(pid, str) or not pid or len(pid) > 64:
                raise ProviderError("Missing PayPal order identity.")
            order.provider_order_id = pid
            # Persist recovered identity before any validation that could fail.
            db.commit()
            verified = provider.retrieve(pid)
            verify_order(order, verified)
            order.approval_url = approval_link(result) or approval_link(verified)
            if not order.approval_url:
                raise ProviderError("Sandbox buyer approval URL was not returned. Reconcile this order.")
            history(db, order, "checkout_ready", "PayPal Sandbox order created. Buyer approval is still required.")
            order.last_error = None
            db.commit()
        except ProviderError as exc:
            uncertain(db, order, exc)


def verify_order(order, result):
    if result.get("id") != order.provider_order_id or result.get("intent") != "CAPTURE":
        raise ProviderError("Provider order identity mismatch.")
    units = result.get("purchase_units", [])
    if len(units) != 1:
        raise ProviderError("Unexpected purchase scope.")
    unit = units[0]
    amount = unit.get("amount", {})
    if (unit.get("reference_id") != order.id or unit.get("custom_id") != order.id
        or unit.get("payee", {}).get("merchant_id") != order.merchant_id
        or amount.get("currency_code") != order.currency or cents(amount.get("value")) != order.amount_cents):
        raise ProviderError("Provider merchant, amount, currency or order reference mismatch.")
    return unit


def task_once(db, order, settings):
    from app.services.commerce.fulfillment import fulfill_paid_order
    fulfill_paid_order(db, order, settings)


def apply_provider_order(db, order, result, settings):
    unit = verify_order(order, result)
    captures = unit.get("payments", {}).get("captures", [])
    if len(captures) > 1:
        raise ProviderError("Unexpected multiple captures. Merchant review required.")
    if captures:
        capture = captures[0]
        amount = capture.get("amount", {})
        if (amount.get("currency_code") != order.currency or cents(amount.get("value")) != order.amount_cents
            or not capture.get("id") or (order.capture_id and order.capture_id != capture["id"])):
            raise ProviderError("Capture details do not match this purchase.")
        status = capture.get("status")
        # Pending captures also have a stable identity needed to match webhooks.
        # Recording that identity never releases fulfillment before COMPLETED.
        order.capture_id = capture["id"]
        if status in {"COMPLETED", "REFUNDED"} and result.get("status") == "COMPLETED":
            order.capture_id = capture["id"]
            if order.payment_state not in {"refund_pending", "refunded"}:
                history(db, order, "paid", "Server verified PayPal Sandbox capture, amount, USD currency and merchant.")
                task_once(db, order, settings)
            return
        if order.payment_state not in {"paid", "refund_pending", "refunded"}:
            history(db, order, "capture_pending" if status == "PENDING" else "failed",
                    "PayPal has not confirmed a completed capture. No coach task was released.")
        return
    if order.payment_state in {"paid", "refund_pending", "refunded"}:
        return  # An old order notification can never undo a confirmed capture/refund.
    if result.get("status") == "VOIDED":
        history(db, order, "canceled", "PayPal order is voided.")
    elif result.get("status") in {"CREATED", "APPROVED", "PAYER_ACTION_REQUIRED"}:
        order.approval_url = approval_link(result) or order.approval_url
        if order.payment_state not in {"canceled", "capture_pending"}:
            history(db, order, "checkout_ready", "Sandbox order retrieved; payment is not yet captured.")


def uncertain(db, order, exc):
    order.last_error = str(exc)
    if order.payment_state not in {"paid", "refund_pending", "refunded"}:
        history(db, order, "uncertain", "Provider outcome uncertain. Use reconciliation before any retry.")
    db.commit()
    raise HTTPException(503, str(exc))


def reconcile_locked(db, order, settings, provider):
    if order.mode == "simulated":
        return
    try:
        result = provider.retrieve(order.provider_order_id)
        apply_provider_order(db, order, result, settings)
        refund = db.query(ReviewRefund).filter_by(order_id=order.id).one_or_none()
        if order.capture_id:
            capture = provider.capture_details(order.capture_id)
            verify_capture_details(order, capture)
            if capture.get("status") == "REFUNDED":
                mark_refunded(db, order, refund)
            elif refund and refund.provider_id:
                apply_refund(db, order, refund, provider.refund_details(refund.provider_id))
        order.last_error = None
        db.commit()
    except ProviderError as exc:
        uncertain(db, order, exc)


def capture_order(db, order, settings, provider):
    with payment_lock(db, order):
        if order.mode != "sandbox":
            raise HTTPException(422, "Use the explicitly labeled simulator for this order.")
        if not order.provider_order_id:
            raise HTTPException(409, "Create or recover the provider order first.")
        # Retrieve before EVERY possible capture retry; a callback is not proof of payment.
        reconcile_locked(db, order, settings, provider)
        if order.payment_state in {"paid", "refunded", "refund_pending", "capture_pending"}:
            return
        if order.payment_state == "canceled":
            raise HTTPException(409, "Checkout was canceled. Start a new review request.")
        result = provider.retrieve(order.provider_order_id)
        verify_order(order, result)
        if result.get("status") != "APPROVED":
            raise HTTPException(409, "Approve this purchase on PayPal Sandbox before capture.")
        check_order_eligibility(db, order, settings)
        retry_window(order.capture_started_at)
        order.capture_started_at = order.capture_started_at or now()
        db.commit()
        try:
            response = provider.capture(order)
            apply_provider_order(db, order, response, settings)
            if order.payment_state not in {"paid", "capture_pending", "refunded"}:
                raise ProviderError("PayPal did not confirm the capture. Reconcile this order.")
            order.last_error = None
            db.commit()
        except ProviderError as exc:
            uncertain(db, order, exc)


def verify_capture_details(order, result):
    amount = result.get("amount", {})
    if result.get("id") != order.capture_id or amount.get("currency_code") != order.currency or cents(amount.get("value")) != order.amount_cents:
        raise ProviderError("Capture reconciliation details mismatch.")
    related = result.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
    if related and related != order.provider_order_id:
        raise ProviderError("Capture belongs to a different order.")


def mark_refunded(db, order, refund):
    if refund:
        refund.state = "completed"
        refund.last_error = None
    history(db, order, "refunded", "Full refund confirmed by the provider; receipt and existing delivered feedback retained.")
    task = db.query(CoachTask).filter_by(order_id=order.id).one_or_none()
    if task and task.status != "delivered":
        task.status = "canceled"
    from app.models.commerce import CoachingCall
    for call in db.query(CoachingCall).filter_by(order_id=order.id):
        if call.status != "completed":
            call.status = "canceled"
        call.meeting_url = call.change_requested_at = call.change_timezone = None


def apply_refund(db, order, refund, result):
    amount = result.get("amount", {})
    if (not result.get("id") or (refund.provider_id and result["id"] != refund.provider_id)
        or amount.get("currency_code") != order.currency or cents(amount.get("value")) != refund.amount_cents
        or refund.amount_cents != order.amount_cents):
        raise ProviderError("Refund amount, currency or identity mismatch.")
    capture_link = [l.get("href", "").rstrip("/").split("/")[-1] for l in result.get("links", []) if l.get("rel") == "up"]
    if order.capture_id not in capture_link:
        raise ProviderError("Refund does not identify the expected capture.")
    refund.provider_id = result["id"]
    if order.payment_state == "refunded" or refund.state == "completed":
        mark_refunded(db, order, refund)
        return
    if result.get("status") == "COMPLETED":
        mark_refunded(db, order, refund)
    elif result.get("status") == "PENDING":
        refund.state = "pending"
        history(db, order, "refund_pending", "Full Sandbox refund requested; awaiting provider confirmation.")
    elif result.get("status") in {"FAILED", "CANCELLED"}:
        if refund.state != "completed" and order.payment_state != "refunded":
            refund.state = "failed"
            refund.last_error = "Provider did not complete the refund. Merchant review required."
            history(db, order, "paid", "Provider refund failed. Capture remains paid; no automatic second refund.")
    else:
        raise ProviderError("Unknown refund status. Reconciliation required.")


def full_refund(db, order, settings, provider):
    with payment_lock(db, order):
        if order.mode == "sandbox":
            reconcile_locked(db, order, settings, provider)
        refund = db.query(ReviewRefund).filter_by(order_id=order.id).one_or_none()
        if order.payment_state == "refunded" or (refund and refund.state in {"pending", "completed", "failed"}):
            return
        if order.payment_state not in {"paid", "refund_pending"} or not order.capture_id:
            raise HTTPException(409, "Only a verified capture can be refunded.")
        if not refund:
            refund = ReviewRefund(order_id=order.id, amount_cents=order.amount_cents)
            db.add(refund)
            db.commit()
        if order.mode == "simulated":
            refund.provider_id = f"SIM-REFUND-{order.id}"
            mark_refunded(db, order, refund)
            db.commit()
            return
        if refund.provider_id:
            apply_refund(db, order, refund, provider.refund_details(refund.provider_id))
            db.commit()
            return
        retry_window(refund.attempted_at)
        refund.attempted_at = refund.attempted_at or now()
        refund.state = "uncertain"
        history(db, order, "refund_pending", "Refund intent and stable request ID saved before provider operation.")
        db.commit()
        try:
            result = provider.refund(order, refund)
            apply_refund(db, order, refund, result)
            db.commit()
        except ProviderError as exc:
            refund.last_error = str(exc)
            order.last_error = "Refund outcome uncertain. Reconcile before retrying the same refund."
            db.commit()
            raise HTTPException(503, order.last_error)


def order_out(db, order, *, coach=False):
    from app.services.commerce.scheduling import calls_out
    from app.services.commerce.handoff import followup_available
    from app.services.commerce.fulfillment import fulfillment_summary
    intake = db.get(ReviewIntake, order.intake_id)
    task = db.query(CoachTask).filter_by(order_id=order.id).one_or_none()
    refund = db.query(ReviewRefund).filter_by(order_id=order.id).one_or_none()
    task_data = None
    if task:
        task_data = {"id": task.id, "status": task.status, "delivered_text": task.delivered_text,
                     "author": task.author, "delivered_at": iso(task.delivered_at)}
        if coach:
            task_data.update(draft=task.draft, draft_source=task.draft_source, revision=task.draft_revision)
        if coach or task.status == "delivered":
            task_data.update(assessment=task.assessment, ai_comparison=task.ai_comparison, next_steps=task.next_steps)
        elif order.payment_state == "paid" and json.loads(order.package_json).get("family") == "agentic":
            # Demo request status is visible after verified payment; draft text stays coach-private until delivery.
            task_data.update(assessment=task.assessment, next_steps=task.next_steps)
    from app.services.commerce.plan_review import context
    plan_review = context(intake)
    context_visible = not coach or order.payment_state == "paid"
    return {"plan_review": plan_review if context_visible else None, "id": order.id, "mode": order.mode, "package": json.loads(order.package_json),
            "amount_cents": order.amount_cents, "currency": order.currency,
            "payment_state": order.payment_state, "provider_order_id": order.provider_order_id,
            "capture_id": order.capture_id, "approval_url": order.approval_url,
            "question": intake.question, "recommendation": json.loads(intake.recommendation_json),
            "shared_context": json.loads(intake.shared_context_json) if intake.shared_context_json and not plan_review and context_visible else None,
            "previous_order_id": intake.previous_order_id, "followup_available": followup_available(db, order),
            "sharing": {"recording_ids": [s.recording_id for s in shares(db, intake.id)],
                        "consented_at": iso(intake.share_consented_at), "ai_consented_at": iso(intake.ai_consented_at)},
            "calls": calls_out(db, order),
            "fulfillment": fulfillment_summary(order, task),
            "task": task_data, "refund": {"state": refund.state, "provider_id": refund.provider_id,
                                          "last_error": refund.last_error} if refund else None,
            "last_error": order.last_error, "created_at": iso(order.created_at),
            "history": [{"state": h.state, "detail": h.detail, "at": iso(h.created_at)}
                        for h in db.query(PaymentHistory).filter_by(order_id=order.id).order_by(PaymentHistory.created_at).all()]}
