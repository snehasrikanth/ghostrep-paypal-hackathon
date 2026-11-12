"""Post-capture fulfillment. Runs only after server-verified completed payment."""
import json
from datetime import datetime, timezone

from app.models.commerce import CoachTask, ReviewIntake
from app.services.commerce.evidence import shared_evidence


def _iso(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def _movement_notes(evidence_rows):
    notes = []
    for clip in evidence_rows:
        for key, fact in clip.get("facts", {}).items():
            if key.startswith("rep_") or key in {"counts", "reported"}:
                text = (fact or {}).get("text")
                if text:
                    notes.append(text)
    return notes[:12]


def build_ai_technique_report(db, order, intake, clips):
    evidence = [shared_evidence(db, rec) for rec in clips if rec]
    notes = _movement_notes(evidence)
    synthetic = any(c.get("synthetic") for c in evidence)
    header = ("DEMO · AI Technique Review\nAutomated report from saved analysis\n"
              "This report assembles your saved movement analysis. No new model call was made. "
              "It has not been reviewed or approved by a live coach.\n\n")
    if synthetic:
        header = "SYNTHETIC DEMO EVIDENCE — not an athlete measurement.\n\n" + header
    body = "Saved movement comparisons\n"
    if notes:
        body += "\n".join(f"- {n}" for n in notes)
    else:
        body += "- Saved analysis was limited; review the replay before changing training."
    question = intake.question if intake else ""
    body += ("\n\nReview prompts\n"
             "- Compare later reps to your personal reference rep in the replay.\n"
             "- Note which comparison differs and discuss any target change with your coach.\n"
             "- Film from a consistent side angle so future comparisons stay meaningful.\n\n"
             f"Athlete question\n{question}\n\n"
             "Limits\nA personal reference is an observed rep, not certified ideal technique. "
             "This demo unlock does not diagnose injury risk or replace a qualified coach.")
    return header + body


def fulfill_paid_order(db, order, settings):
    """Idempotent fulfillment after verified capture. Never trusts frontend success state."""
    from app.services.commerce.orders import check_order_eligibility, selected_clips

    package = json.loads(order.package_json)
    check_order_eligibility(db, order, settings)
    task = db.query(CoachTask).filter_by(order_id=order.id).one_or_none()
    if task is None:
        task = CoachTask(order_id=order.id)
        db.add(task)
        db.flush()

    kind = package.get("kind")
    family = package.get("family")
    intake = db.get(ReviewIntake, order.intake_id)
    clips = selected_clips(db, intake) if intake else []
    from app.services.commerce.plan_review import context
    saved_plan = context(intake) if intake else None
    if saved_plan:
        if task.status == "queued" and not task.draft:
            task.draft_source = "plan_review_request"
            task.draft = "Review the shared training plan against the athlete’s restrictions and preferences."
            task.assessment = "Plan review requested. Coach match and availability pending confirmation."
            task.next_steps = "Your coach will confirm the preferred time and provide a meeting link."
        # The preferred time remains an availability request, never a confirmed reservation.
        from app.models.commerce import CoachingCall
        if not db.query(CoachingCall).filter_by(order_id=order.id).first():
            prefs = saved_plan["preferences"]
            db.add(CoachingCall(order_id=order.id, session_index=1,
                               requested_at=datetime.fromisoformat(prefs["preferred_at"]),
                               requested_timezone=prefs["timezone"], status="requested"))
        return task


    if family == "agentic" and kind == "ai_report":
        if task.status != "delivered":
            task.delivered_text = build_ai_technique_report(db, order, intake, clips)
            task.author = "GhostRep · automated saved-evidence review"
            task.delivered_at = datetime.now(timezone.utc)
            task.status = "delivered"
            task.draft_source = "ai_technique_review"
            task.assessment = "AI Technique Review unlocked after verified PayPal Sandbox capture."
            task.next_steps = "Use the corrective focus above with your replay. Human coaching remains optional."
        return task

    if family == "agentic" and kind == "written_review":
        if task.status == "queued" and not task.draft:
            task.draft = ("DEMO coaching request — Expert Video Review.\n"
                          "A human coach has not reviewed this yet. No credentials or delivery timeline are implied.\n\n"
                          f"Athlete question: {intake.question if intake else ''}\n")
            task.draft_source = "expert_video_request"
            task.assessment = "Pending human review (demo workflow)."
        return task

    if family == "agentic" and kind == "live_calls":
        if task.status == "queued" and not task.draft:
            task.draft = ("DEMO booking request — Personal Coaching Session.\n"
                          "Status: pending confirmation. No real coach has been hired or scheduled automatically.\n\n"
                          f"Athlete question: {intake.question if intake else ''}\n")
            task.draft_source = "personal_session_booking"
            task.assessment = "Booking request pending confirmation (demo)."
            task.next_steps = "Athlete may request a preferred time after payment. Confirmation is manual/demo."
        return task

    # Instructor / legacy packages: queued human task only.
    return task


def fulfillment_summary(order, task):
    package = json.loads(order.package_json)
    paid = order.payment_state == "paid"
    return {
        "family": package.get("family"),
        "kind": package.get("kind"),
        "human_delivery": bool(package.get("human_delivery")),
        "delivery_label": package.get("delivery_label") or package.get("name"),
        "unlocked": bool(paid and task and (
            package.get("kind") != "ai_report" or task.status == "delivered"
        )),
        "status": task.status if task else ("locked" if not paid else "pending"),
        "demo_notice": (
            "Demo coaching workflow. Automated feedback and live coach review are separate services. Live coaching requires confirmation."
            if package.get("family") == "agentic" else None
        ),
        "delivered_at": _iso(task.delivered_at) if task else None,
    }
