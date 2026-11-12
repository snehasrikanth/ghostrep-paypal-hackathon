"""Private, buyer-requested scheduling for purchased calls; no calendar or video provider API."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import update

from app.models.commerce import CoachingCall, ReviewOrder


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def zone(name):
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError):
        raise HTTPException(422, "Choose a valid local time zone, then request your time again.")


def future(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(422, "Include the time zone with your requested time.")
    value = utc(value)
    if not datetime.now(timezone.utc) + timedelta(hours=1) <= value <= datetime.now(timezone.utc) + timedelta(days=90):
        raise HTTPException(422, "Choose a time at least one hour ahead and within the next 90 days.")
    return value


def plan(order):
    package = json.loads(order.package_json)
    if package.get("kind") != "live_calls":
        raise HTTPException(422, "This purchase does not include video calls.")
    if order.payment_state != "paid":
        raise HTTPException(409, "Scheduling is available after confirmed payment and while no refund is pending.")
    return package


def calls_out(db, order):
    available = order.payment_state == "paid"
    return [{"id": c.id, "session_index": c.session_index, "requested_at": utc(c.requested_at).isoformat(),
             "requested_timezone": c.requested_timezone,
             "change_requested_at": utc(c.change_requested_at).isoformat() if c.change_requested_at else None,
             "change_timezone": c.change_timezone,
             "starts_at": utc(c.starts_at).isoformat() if c.starts_at else None,
             "meeting_url": c.meeting_url if available and c.status == "confirmed" else None,
             "status": c.status if available else "paused"}
            for c in db.query(CoachingCall).filter_by(order_id=order.id).order_by(CoachingCall.session_index)]


def load_call(db, order, call_id):
    call = db.query(CoachingCall).filter_by(id=call_id, order_id=order.id).one_or_none()
    if call is None:
        raise HTTPException(404, "Call not found.")
    return call


def month_window(db, order, package, start):
    if package["session_count"] <= 1:
        return
    anchor = order.schedule_anchor
    if anchor is None:
        # Older schedules acquire an anchor without changing their purchased terms.
        rows = db.query(CoachingCall).filter_by(order_id=order.id).all()
        anchor = min(utc(c.requested_at) for c in rows)
        order.schedule_anchor = anchor
    if not utc(anchor) - timedelta(days=1) <= start <= utc(anchor) + timedelta(days=30):
        raise HTTPException(422, "Choose a monthly call time within 30 days of your first requested call.")


def request_calls(db, order, starts_at, timezone_name="UTC"):
    package = plan(order)
    first = future(starts_at)
    tz = zone(timezone_name)
    existing = db.query(CoachingCall).filter_by(order_id=order.id).all()
    if any(c.status in {"confirmed", "completed"} for c in existing):
        raise HTTPException(409, "Use Change time on the individual call. Your other appointments will stay as they are.")
    order.schedule_anchor = first
    # Add weeks in the athlete's zone, preserving wall time across daylight-saving changes.
    local_first = first.astimezone(tz)
    for index in range(1, package["session_count"] + 1):
        call = next((c for c in existing if c.session_index == index), None)
        if call is None:
            call = CoachingCall(order_id=order.id, session_index=index)
            db.add(call)
        call.requested_at = (local_first + timedelta(weeks=index - 1)).astimezone(timezone.utc)
        call.requested_timezone = timezone_name
        call.status, call.starts_at, call.meeting_url = "requested", None, None
        call.change_requested_at = call.change_timezone = None
    db.commit()


def request_call_change(db, order, call_id, starts_at, timezone_name="UTC"):
    package = plan(order)
    start = future(starts_at)
    zone(timezone_name)
    call = load_call(db, order, call_id)
    if call.status == "completed":
        raise HTTPException(409, "This call is completed. Your remaining calls can still be scheduled.")
    month_window(db, order, package, start)
    if call.status == "confirmed":
        # Keep the booked time/link until the coach confirms the requested replacement.
        call.change_requested_at, call.change_timezone = start, timezone_name
    else:
        call.requested_at, call.requested_timezone, call.status = start, timezone_name, "requested"
        call.starts_at = call.meeting_url = call.change_requested_at = call.change_timezone = None
    db.commit()


def confirm_call(db, order, call_id, starts_at, meeting_url):
    package = plan(order)
    start = future(starts_at)
    meeting_url = meeting_url.strip()
    try:
        parsed = urlparse(meeting_url)
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(422, "Use a valid HTTPS meeting link.") from exc
    host = parsed.hostname or ""
    allowed = host in {"meet.google.com", "zoom.us", "www.zoom.us", "teams.microsoft.com", "teams.live.com"} or host.endswith(".zoom.us")
    if parsed.scheme != "https" or not allowed or parsed.path in {"", "/"}:
        raise HTTPException(422, "Use an HTTPS Google Meet, Zoom or Microsoft Teams meeting link for this appointment.")
    if parsed.username or parsed.password or port not in {None, 443}:
        raise HTTPException(422, "Use a meeting link without a username, password or custom port.")
    call = load_call(db, order, call_id)
    if call.status in {"completed", "canceled"}:
        raise HTTPException(409, "Request a new time for a canceled call before confirming it. Completed calls cannot be changed.")
    month_window(db, order, package, start)
    # SQLite serializes this write across ALL orders before the overlap read.
    db.execute(update(CoachingCall).where(CoachingCall.id == call.id).values(status=call.status))
    end = start + timedelta(minutes=package["session_minutes"])
    for other, other_order in db.query(CoachingCall, ReviewOrder).join(ReviewOrder, ReviewOrder.id == CoachingCall.order_id).filter(
        CoachingCall.id != call.id, CoachingCall.status == "confirmed", ReviewOrder.payment_state.in_(["paid", "refund_pending"]),
        ReviewOrder.mode == order.mode).all():
        other_start = utc(other.starts_at)
        other_end = other_start + timedelta(minutes=json.loads(other_order.package_json)["session_minutes"])
        if start < other_end and other_start < end:
            raise HTTPException(409, "This time overlaps another confirmed call. Choose a different time.")
    if call.change_requested_at:
        # Retain the latest preferred time as distinct from the confirmed appointment.
        call.requested_at, call.requested_timezone = call.change_requested_at, call.change_timezone or call.requested_timezone
    call.starts_at, call.meeting_url, call.status = start, meeting_url, "confirmed"
    call.change_requested_at = call.change_timezone = None
    db.commit()


def cancel_call(db, order, call_id):
    plan(order)
    call = load_call(db, order, call_id)
    if call.status == "completed":
        raise HTTPException(409, "A completed call cannot be canceled.")
    call.status = "canceled"
    call.meeting_url = call.change_requested_at = call.change_timezone = None
    db.commit()


def complete_call(db, order, call_id):
    plan(order)
    call = load_call(db, order, call_id)
    if call.status == "completed":
        return
    if call.status != "confirmed" or utc(call.starts_at) > datetime.now(timezone.utc):
        raise HTTPException(409, "Only a confirmed call whose start time has passed can be completed.")
    call.status = "completed"
    call.meeting_url = call.change_requested_at = call.change_timezone = None
    db.commit()
