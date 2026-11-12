"""Include the supported video exercise without inventing equipment or overriding restrictions."""
from copy import deepcopy
from app.services.workout.catalog import validate_exercise
from app.services.workout.profile_model import planner_view

EXERCISE = "barbell_squat"
NOTE = "Video check-in: record this technique set using your familiar setup. No working load is prescribed for this check."


def requirement(profile, exercises=()):
    view = planner_view(profile)
    result = {"exercise_id": EXERCISE, "required": True, "eligible": False, "included": False}
    if EXERCISE in view.get("avoided_exercises", []):
        return {**result, "status": "restricted", "reason": "Barbell squats are excluded in your saved preferences. Review the plan with your coach; other exercises support recording and logging."}
    allowed, _ = validate_exercise(EXERCISE, ["barbell", "bodyweight"], view["limitations"])
    if not allowed:
        return {**result, "status": "restricted", "reason": "Your saved movement restrictions exclude this check. Keep your existing workout and ask your coach about suitable exercise choices."}
    if view.get("familiarity", {}).get(EXERCISE) == "new":
        return {**result, "status": "coach_setup", "reason": "You marked barbell squats as new. Review the setup with a coach before adding the video check-in."}
    if "barbell" not in view["equipment"]:
        return {**result, "status": "equipment_required", "reason": "Your equipment list does not include a barbell. Confirm access to a barbell and rack to add the supported video-analysis exercise."}
    included = any(e.get("exercise_id") == EXERCISE for e in exercises)
    return {**result, "eligible": True, "included": included, "status": "included" if included else "ready_to_add",
            "reason": "Barbell squat is the supported video-analysis exercise. It is included in every eligible workout; other lifts keep their video replay and training log."}


def check_exercise():
    return {"exercise_id": EXERCISE, "sets": 1, "target_reps": 5, "rest_seconds": 60, "suggested_load_kg": None, "notes": NOTE, "is_analysis_check": True}


def include_check(plan_data, profile):
    result = deepcopy(plan_data)
    def apply(row):
        exercises = list(row.get("exercises") or [])
        check = requirement(profile, exercises)
        if check["eligible"] and not check["included"]:
            exercises.append(check_exercise())
            row["exercises"] = exercises
            if row.get("estimated_minutes") is not None:
                from app.services.workout.local_planner import estimate_minutes
                row["estimated_minutes"] = estimate_minutes(exercises)
        row["analysis_requirement"] = requirement(profile, exercises)
        if row["analysis_requirement"]["included"] and row.get("notes"):
            row["notes"] = row["notes"].replace("Log these sets by hand. Video analysis covers barbell squat only.", "Record your barbell squat for analysis. Other lifts support recording and logging.")
    apply(result)
    for session in result.get("schedule") or []:
        apply(session)
    return result
