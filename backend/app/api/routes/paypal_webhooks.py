import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import settings_dep
from app.api.routes.reviews import provider_dep
from app.database import get_db
from app.models.commerce import ReviewOrder, ReviewRefund, WebhookEvent
from app.services.commerce.orders import apply_refund, payment_lock, reconcile_locked
from app.services.commerce.paypal import ProviderError, cents

router = APIRouter(tags=["PayPal Sandbox webhook"])
EVENTS = {"CHECKOUT.ORDER.APPROVED", "CHECKOUT.ORDER.COMPLETED", "PAYMENT.CAPTURE.COMPLETED",
          "PAYMENT.CAPTURE.PENDING", "PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED",
          "PAYMENT.REFUND.PENDING", "PAYMENT.REFUND.FAILED"}


@router.post("/reviews/paypal/webhook")
async def webhook(request: Request, db: Session = Depends(get_db), settings=Depends(settings_dep), provider=Depends(provider_dep)):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, "Webhook too large.")
    try:
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError()
        eid, kind, resource = event["id"], event["event_type"], event["resource"]
        if not isinstance(resource, dict) or not all(isinstance(v, str) and 0 < len(v) <= 128 for v in (eid, kind, resource.get("id"))):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise HTTPException(400, "Invalid webhook envelope.")
    try:
        if not provider.verify_webhook(request.headers, event):
            raise HTTPException(400, "Invalid PayPal webhook signature.")
    except ProviderError:
        raise HTTPException(503, "PayPal signature verification unavailable; retry required.")
    if db.get(WebhookEvent, eid):
        return {"ok": True, "duplicate": True}
    if kind not in EVENTS:
        return {"ok": True, "ignored": True}
    related = resource.get("supplementary_data", {}).get("related_ids", {})
    provider_order_id = resource["id"] if kind.startswith("CHECKOUT.ORDER.") else related.get("order_id")
    order = db.query(ReviewOrder).filter_by(provider_order_id=provider_order_id, mode="sandbox").one_or_none() if provider_order_id else None
    is_refund = "REFUND" in kind
    capture_id = related.get("capture_id")
    if is_refund:
        for link in resource.get("links", []):
            if link.get("rel") == "up":
                capture_id = link.get("href", "").rstrip("/").split("/")[-1]
    elif kind.startswith("PAYMENT.CAPTURE."):
        capture_id = resource["id"]
    if not order and capture_id:
        order = db.query(ReviewOrder).filter_by(capture_id=capture_id, mode="sandbox").one_or_none()
    if not order:
        # No unknown event is allowed to create a purchase or grant access.
        return {"ok": True, "ignored": True}
    with payment_lock(db, order):
        if db.get(WebhookEvent, eid):
            return {"ok": True, "duplicate": True}
        # Signed events are notifications, not authoritative state. Retrieve current resources.
        reconcile_locked(db, order, settings, provider)
        if kind.startswith("PAYMENT."):
            amount = resource.get("amount", {})
            if (amount.get("currency_code") != order.currency or cents(amount.get("value")) != order.amount_cents
                or capture_id != order.capture_id):
                raise HTTPException(400, "Webhook resource or amount does not match the stored purchase.")
        if is_refund:
            try:
                result = provider.refund_details(resource["id"])
                refund = db.query(ReviewRefund).filter_by(order_id=order.id).one_or_none()
                if not refund:
                    refund = ReviewRefund(order_id=order.id, amount_cents=order.amount_cents)
                    db.add(refund)
                apply_refund(db, order, refund, result)
            except ProviderError:
                raise HTTPException(503, "Refund resource could not be reconciled; retry required.")
        db.add(WebhookEvent(event_id=eid, event_type=kind, resource_id=resource["id"], disposition="reconciled"))
        db.commit()
    return {"ok": True}
