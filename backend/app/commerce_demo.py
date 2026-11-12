"""Seed the original synthetic journal plus two isolated squat-analysis fixtures."""
from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models.entities import RecordedSet, WorkoutSession
from app.services.demo.identity import DEMO_USER_ID, demo_id
from app.services.demo.seed import seed_demo
from app.services.video.jobs import VideoJobRunner


def main():
    settings = get_settings()
    if not settings.simulator_available:
        raise SystemExit("Commerce fixtures are development-only.")
    init_db()
    with SessionLocal() as db:
        print(seed_demo(db, timezone_name="America/New_York").as_text())
        session_id = demo_id("coach-review-fixtures")
        if not db.get(WorkoutSession, session_id):
            db.add(WorkoutSession(id=session_id, user_id=DEMO_USER_ID, status="sample"))
            db.commit()
        runner = VideoJobRunner(settings.model_copy(update={"enable_meta_api": False, "ai_provider": "local",
                    "coaching_provider": "local", "workout_provider": "local", "segmentation_provider": "none"}))
        for index in (1, 2):
            rid = demo_id("coach-review-clip", str(index))
            if db.get(RecordedSet, rid):
                continue
            rec = RecordedSet(id=rid, session_id=session_id, user_id=DEMO_USER_ID, exercise_id="barbell_squat",
                entry_source="demo", original_filename="DEMO_FIXTURE", set_index=index, target_reps=6,
                processing_status="UPLOADED", analysis_requested=True, consent_version="synthetic-demo-only")
            db.add(rec); db.commit()
            runner._process(db, rid, demo=True, approval_token=None)
        print("Two synthetic coach-review fixtures ready. No private video, PayPal request or model call used.")


if __name__ == "__main__":
    main()
