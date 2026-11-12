from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.workout.analysis_check import include_check, requirement
from tests.test_plan_experience import profile


def test_every_eligible_workout_has_one_supported_squat_without_replacing_work():
    athlete = profile("upper_lower")
    original = {"name": "Upper", "exercises": [{"exercise_id": "bench_press", "sets": 3, "target_reps": 8, "rest_seconds": 90}],
                "schedule": [{"workout_name": "Upper", "session_type": "upper", "exercises": [{"exercise_id": "bench_press", "sets": 3, "target_reps": 8, "rest_seconds": 90}]}]}
    before = deepcopy(original)
    result = include_check(original, athlete)
    assert original == before
    assert result["exercises"][0] == before["exercises"][0]
    assert result["exercises"][-1]["exercise_id"] == "barbell_squat"
    assert result["exercises"][-1]["sets"] == 1
    assert result["exercises"][-1]["suggested_load_kg"] is None
    assert result["exercises"][-1]["is_analysis_check"] is True
    assert result["schedule"][0]["analysis_requirement"]["included"] is True
    assert include_check(result, athlete) == result


@pytest.mark.parametrize("condition,status", [("equipment", "equipment_required"), ("excluded", "restricted"), ("restriction", "restricted"), ("new", "coach_setup")])
def test_requirement_never_overrides_saved_constraints(condition, status):
    athlete = profile("upper_lower")
    a = athlete["assessment"]
    if condition == "equipment": a["equipment"]["available"] = ["dumbbells", "bodyweight"]
    if condition == "excluded": a["considerations"]["avoided_exercises"] = ["barbell_squat"]
    if condition == "restriction": a["considerations"]["movement_restrictions"] = ["acute back pain"]
    if condition == "new": a["experience"]["exercise_familiarity"] = {"barbell_squat": "new"}
    assert requirement(athlete)["status"] == status
    assert include_check({"exercises": []}, athlete)["exercises"] == []


def test_equipment_confirmation_adds_check_without_replacing_workout_or_logged_sets():
    athlete = profile("upper_lower")
    athlete["assessment"]["equipment"]["available"] = ["dumbbells", "bodyweight"]
    with TestClient(app) as client:
        assert client.post("/profiles", json=athlete).status_code == 200
        proposed = client.post("/workouts/generate", json={}).json()
        plan = client.post(f"/workouts/{proposed['id']}/accept").json()
        session = client.post("/sessions", json={"plan_id": plan["id"]}).json()
        logged = client.post(f"/sessions/{session['id']}/sets", json={"exercise_id": plan["exercises"][0]["exercise_id"], "set_index": 1, "completed_reps": 5, "load_kg": 8}).json()
        original_ids = [e["id"] for e in plan["exercises"]]
        assert client.get(f"/workouts/{plan['id']}").json()["analysis_requirement"]["status"] == "equipment_required"
        path = f"/workouts/{plan['id']}/barbell-check"
        assert client.post(path, json={}).status_code == 409
        response = client.post(path, json={"confirm_barbell_access": True})
        assert response.status_code == 200, response.text
        updated = response.json()
        assert updated["analysis_requirement"]["included"] is True
        assert [e["id"] for e in updated["exercises"]][:-1] == original_ids
        assert updated["exercises"][-1]["exercise_id"] == "barbell_squat"
        assert all(any(e["exercise_id"] == "barbell_squat" for e in day["exercises"]) for day in updated["schedule"])
        repeated = client.post(path, json={"confirm_barbell_access": True}).json()
        assert len(repeated["exercises"]) == len(updated["exercises"])
        assert "barbell" in client.get("/profiles/me").json()["equipment"]
        assert client.get(f"/sessions/{session['id']}").json()["sets"][0]["id"] == logged["id"]
        with TestClient(app) as other:
            assert other.post(path, json={"confirm_barbell_access": True}).status_code == 404


def test_equipment_confirmation_cannot_override_a_movement_restriction():
    athlete = profile("upper_lower")
    athlete["assessment"]["equipment"]["available"] = ["dumbbells", "bodyweight"]
    athlete["assessment"]["considerations"]["avoided_exercises"] = ["barbell_squat"]
    with TestClient(app) as client:
        client.post("/profiles", json=athlete)
        plan = client.post("/workouts/generate", json={}).json()
        response = client.post(f"/workouts/{plan['id']}/barbell-check", json={"confirm_barbell_access": True})
        assert response.status_code == 409
        assert "barbell" not in client.get("/profiles/me").json()["equipment"]
