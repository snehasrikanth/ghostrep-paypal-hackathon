"""Consented plan-only coaching. No video, model calls or invented coach availability."""
import json
import hashlib
from fastapi import HTTPException
from app.models.entities import WorkoutPlan, Profile
from app.services.demo.identity import DEMO_USER_ID
from app.api.serialize import plan_out


def snapshot(db, user_id, plan_id, settings):
    plan = db.get(WorkoutPlan, plan_id)
    if not plan or plan.user_id != user_id:
        raise HTTPException(404, "Plan not found.")
    simulated = user_id == DEMO_USER_ID
    if simulated and not settings.simulator_available:
        raise HTTPException(403, "Demo plan review is disabled in this environment.")
    profile = db.query(Profile).filter_by(user_id=user_id).one_or_none()
    from app.api.serialize import profile_out
    assessment = profile_out(profile)["assessment"] if profile else {}
    saved = {"kind": "plan_review", "plan_id": plan.id, "plan": plan_out(plan), "mode": "simulated" if simulated else "sandbox",
            "restrictions": json.loads(profile.limitations_json or "[]") if profile else [],
            "training_preferences": {k: assessment[k] for k in ("goals", "experience", "schedule", "preferences", "equipment", "considerations") if k in assessment}}
    saved["fingerprint"] = hashlib.sha256(json.dumps(saved, sort_keys=True).encode()).hexdigest()
    return saved


def context(intake):
    saved = json.loads(intake.shared_context_json or "{}")
    return saved if saved.get("kind") == "plan_review" else None


def validate(db, intake, package, settings):
    saved = context(intake)
    if not saved:
        raise HTTPException(409, "Plan review context is missing.")
    plan = db.get(WorkoutPlan, saved.get("plan_id"))
    if not plan or plan.user_id != intake.user_id:
        raise HTTPException(404, "Plan not found.")
    expected_mode = "simulated" if intake.user_id == DEMO_USER_ID else "sandbox"
    if intake.mode != expected_mode or (expected_mode == "simulated" and not settings.simulator_available):
        raise HTTPException(403, "Plan review payment mode is unavailable for this athlete.")
    if package.get("id") != "personal-coaching-session":
        raise HTTPException(422, "Plan reviews require the fixed-price Personal Coaching Session in PayPal Sandbox.")
    return saved
