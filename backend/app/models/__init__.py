from app.models import commerce  # noqa: F401 — register additive commerce metadata
from app.models.entities import (
    AnalysisResult,
    CoachingDecision,
    CoachingVersion,
    ConsentRecord,
    MetaUsageEvent,
    Profile,
    RecordedSet,
    RepMetric,
    User,
    UserSession,
    WorkoutExercise,
    WorkoutPlan,
    WorkoutSession,
)

__all__ = [
    "AnalysisResult",
    "CoachingDecision",
    "CoachingVersion",
    "ConsentRecord",
    "MetaUsageEvent",
    "Profile",
    "RecordedSet",
    "RepMetric",
    "User",
    "UserSession",
    "WorkoutExercise",
    "WorkoutPlan",
    "WorkoutSession",
]
