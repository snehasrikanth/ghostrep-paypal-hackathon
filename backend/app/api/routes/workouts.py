import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import current_user, get_db, settings_dep
from app.api.serialize import plan_out
from app.config import Settings
from app.models.entities import Profile, User, WorkoutExercise, WorkoutPlan
from app.schemas.workout import WorkoutGenerateIn, WorkoutPatchIn, BarbellCheckIn
from app.services.meta.errors import MetaError, MetaRejected
from app.services.meta.gateway import MetaBlocked, MetaGateway
from app.services.meta.muse import MuseProvider
from app.services.meta.request_approval import muse_request
from app.services.workout.catalog import validate_exercise
from app.services.workout.history import completed_training_session_count, recent_training_context
from app.services.meta.saved_results import (
    SavedResultError,
    load_json,
    plan_data_from_public,
    public_workout,
    saved_workout_path,
)
from app.services.workout.proposals import (
    accept_proposal,
    discard_proposal,
    latest_proposal,
    owned_plan,
    persist_proposal,
)

router = APIRouter(prefix="/workouts", tags=["workouts"])


def _profile_dict(db: Session, row: Profile) -> dict:
    return {
        "goal": row.goal,
        "experience": row.experience,
        "days_per_week": row.days_per_week,
        "session_duration_minutes": row.session_duration_minutes,
        "equipment": json.loads(row.equipment_json),
        "current_squat_load_kg": row.current_squat_load_kg,
        "limitations": json.loads(row.limitations_json or "[]"),
        "assessment": json.loads(row.assessment_json) if row.assessment_json else None,
        "display_name": None,
        "recent_sessions": recent_training_context(db, row.user_id),
    }


@router.post("/generate")
def generate_workout(
    payload: WorkoutGenerateIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(settings_dep),
) -> dict:
    profile = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
    if not profile or not profile.submitted:
        raise HTTPException(status_code=400, detail="Create a profile before generating a workout.")
    session_index = completed_training_session_count(db, user.id)
    profile_payload = _profile_dict(db, profile)
    try:
        request_settings, approval = muse_request(settings, "workout_generation", payload.approve_meta_spend)
        provider = MuseProvider(request_settings, MetaGateway(request_settings, db))
        plan_data = provider.generate_workout(profile_payload, payload.focus, approval_token=approval, session_index=session_index)
    except MetaBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MetaRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MetaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    plan = persist_proposal(
        db,
        user,
        plan_data,
        profile_payload,
        session_index,
        payload.focus,
        profile_payload["recent_sessions"],
    )
    return plan_out(plan)


@router.get("")
def list_workouts(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    rows = (
        db.query(WorkoutPlan)
        .filter(WorkoutPlan.user_id == user.id)
        .order_by(WorkoutPlan.created_at.desc())
        .all()
    )
    return {"plans": [plan_out(p) for p in rows]}


@router.get("/next")
def next_workout(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """The accepted plan the athlete should do next, or null when every plan is done."""
    row = (
        db.query(WorkoutPlan)
        .filter(WorkoutPlan.user_id == user.id, WorkoutPlan.status == "active")
        .order_by(WorkoutPlan.created_at.desc())
        .first()
    )
    return {"plan": plan_out(row) if row else None}


@router.get("/proposal")
def get_proposal(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    row = latest_proposal(db, user)
    return {"plan": plan_out(row) if row else None}


@router.get("/saved-live")
def get_saved_live(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """Display a completed Muse week from disk. Viewing does not persist or call the model."""
    profile = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
    raw = load_json(saved_workout_path(settings))
    if raw is None:
        return {"available": False}
    try:
        return public_workout(raw, _profile_dict(db, profile) if profile else {})
    except SavedResultError as exc:
        return {"available": False, "reason": str(exc)}


@router.post("/import-saved")
def import_saved_workout(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(settings_dep),
) -> dict:
    """Copy the saved Muse week into a reviewable proposal. Does not call Muse."""
    profile = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
    if not profile or not profile.submitted:
        raise HTTPException(status_code=400, detail="Create a profile before importing a saved week.")
    raw = load_json(saved_workout_path(settings))
    if raw is None:
        raise HTTPException(status_code=404, detail="No saved live Muse week is on disk.")
    profile_payload = _profile_dict(db, profile)
    try:
        public = public_workout(raw, profile_payload)
        plan_data = plan_data_from_public(public)
    except SavedResultError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session_index = completed_training_session_count(db, user.id)
    plan = persist_proposal(
        db,
        user,
        plan_data,
        profile_payload,
        session_index,
        None,
        profile_payload["recent_sessions"],
        artifact_id=public["attempt_id"],
    )
    return plan_out(plan)


@router.post("/{plan_id}/accept")
def accept_workout(plan_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    plan = accept_proposal(db, user, owned_plan(db, user, plan_id))
    return plan_out(plan)


@router.post("/{plan_id}/discard")
def discard_workout(plan_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    discard_proposal(db, user, owned_plan(db, user, plan_id))
    row = (
        db.query(WorkoutPlan)
        .filter(WorkoutPlan.user_id == user.id, WorkoutPlan.status == "active")
        .order_by(WorkoutPlan.created_at.desc())
        .first()
    )
    return {"plan": plan_out(row) if row else None, "discarded": True}


@router.get("/{plan_id}")
def get_workout(plan_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    plan = db.get(WorkoutPlan, plan_id)
    if not plan or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    result = plan_out(plan)
    profile = db.query(Profile).filter_by(user_id=user.id).one_or_none()
    if profile:
        from app.services.workout.analysis_check import requirement
        result["analysis_requirement"] = requirement(_profile_dict(db, profile), [{"exercise_id": e.exercise_id} for e in plan.exercises])
    return result


@router.post("/{plan_id}/barbell-check")
def add_barbell_check(plan_id: str, body: BarbellCheckIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    from app.services.demo.identity import DEMO_USER_ID
    from app.services.workout.analysis_check import requirement, check_exercise
    from app.services.workout.profile_model import assessment_from_legacy
    from copy import deepcopy
    plan = owned_plan(db, user, plan_id)
    if user.id == DEMO_USER_ID or plan.status not in {"active", "proposed"}:
        raise HTTPException(409, "This saved workout cannot be changed. Build a new plan to add the check-in.")
    profile = db.query(Profile).filter_by(user_id=user.id).one_or_none()
    if not profile:
        raise HTTPException(409, "Complete your training profile first.")
    data = _profile_dict(db, profile)
    if body.confirm_barbell_access:
        data = deepcopy(data)
        data["equipment"] = list(dict.fromkeys(data["equipment"] + ["barbell", "rack"]))
        assessment = data.get("assessment") or assessment_from_legacy(data)
        assessment.setdefault("equipment", {})["available"] = list(dict.fromkeys(assessment.get("equipment", {}).get("available", []) + ["barbell", "squat_rack"]))
        assessment["equipment"]["preset"] = "custom"
        data["assessment"] = assessment
    check = requirement(data, [{"exercise_id": e.exercise_id} for e in plan.exercises])
    if not check["eligible"]:
        raise HTTPException(409, check["reason"])
    if body.confirm_barbell_access:
        profile.equipment_json = json.dumps(data["equipment"])
        profile.assessment_json = json.dumps(data["assessment"])
    if not check["included"]:
        exercise = check_exercise()
        exercise.pop("is_analysis_check", None)
        db.add(WorkoutExercise(plan_id=plan.id, position=max((e.position for e in plan.exercises), default=-1)+1, **exercise))
        if plan.estimated_minutes is not None:
            from app.services.workout.local_planner import estimate_minutes
            plan.estimated_minutes = estimate_minutes([
                {"exercise_id": ex.exercise_id, "sets": ex.sets, "target_reps": ex.target_reps, "rest_seconds": ex.rest_seconds}
                for ex in plan.exercises
            ] + [check_exercise()])
    if plan.schedule_json:
        from app.services.workout.analysis_check import include_check
        schedule = include_check({"exercises": [], "schedule": json.loads(plan.schedule_json)}, data)["schedule"]
        plan.schedule_json = json.dumps(schedule)
    context = json.loads(plan.context_json or "{}")
    context.setdefault("inputs", {})["equipment"] = data["equipment"]
    context["analysis_requirement"] = {**check, "included": True, "status": "included"}
    plan.context_json = json.dumps(context)
    db.commit(); db.refresh(plan)
    # Reload the relationship after adding a row; recorded/logged sets are never replaced.
    db.expire(plan, ["exercises"])
    return plan_out(plan)


@router.patch("/{plan_id}")
def patch_workout(
    plan_id: str,
    payload: WorkoutPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    plan = db.get(WorkoutPlan, plan_id)
    if not plan or plan.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.name:
        plan.name = payload.name
    if payload.exercises is not None:
        profile = db.query(Profile).filter(Profile.user_id == user.id).one_or_none()
        equipment = json.loads(profile.equipment_json) if profile else ["bodyweight"]
        limitations = json.loads(profile.limitations_json) if profile else []
        db.query(WorkoutExercise).filter(WorkoutExercise.plan_id == plan.id).delete()
        for index, item in enumerate(payload.exercises):
            ok, reason = validate_exercise(item.exercise_id, equipment + ["bodyweight"], limitations)
            if not ok:
                raise HTTPException(status_code=400, detail=reason)
            db.add(
                WorkoutExercise(
                    plan_id=plan.id,
                    exercise_id=item.exercise_id,
                    position=index,
                    sets=item.sets,
                    target_reps=item.target_reps,
                    rest_seconds=item.rest_seconds,
                    suggested_load_kg=item.suggested_load_kg,
                    notes=item.notes,
                )
            )
    db.commit()
    db.refresh(plan)
    return plan_out(plan)
