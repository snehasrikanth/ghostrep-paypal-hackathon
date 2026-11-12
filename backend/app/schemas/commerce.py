from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntakeBody(StrictBody):
    question: str = Field(min_length=1, max_length=1200)
    budget_cents: int | None = Field(default=None, ge=0, le=100000, strict=True)
    recording_ids: list[str] = Field(min_length=1, max_length=2)
    share_with_coach: bool
    ai_consent: bool = False
    mode: Literal["sandbox", "simulated"] = "sandbox"
    share_ai_context: bool = False
    context_fingerprint: str | None = Field(default=None, min_length=64, max_length=64)
    previous_order_id: str | None = None


class CheckoutBody(StrictBody):
    intake_id: str
    package_id: str
    checkout_key: str = Field(min_length=16, max_length=64)
    # Explicit buyer approval is required before PayPal checkout is initiated.
    approved: bool = False


class PaymentCheckoutBody(CheckoutBody):
    """Payments checkout requires an explicit approved=true from the athlete."""
    approved: bool = False


class AgenticIntakeBody(IntakeBody):
    """Agentic commerce intake. Defaults keep Meta/AI consent off unless the athlete opts in."""
    share_with_coach: bool = True
    ai_consent: bool = False


class CoachLogin(StrictBody):
    password: str = Field(min_length=1, max_length=256)


class DraftBody(StrictBody):
    text: str = Field(default="", max_length=10000)
    revision: int = Field(ge=0)
    assessment: str | None = Field(default=None, max_length=3000)
    ai_comparison: str | None = Field(default=None, max_length=3000)
    next_steps: str | None = Field(default=None, max_length=3000)


class DeliveryBody(StrictBody):
    reviewed_and_approved: bool
    revision: int = Field(ge=0)


class AIApproval(StrictBody):
    ai_consent: bool = False


class SimulateBody(StrictBody):
    result: Literal["completed", "pending", "failed"] = "completed"


class CallRequest(StrictBody):
    starts_at: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=80)


class CallConfirmation(CallRequest):
    meeting_url: str = Field(min_length=10, max_length=1000)


class CoachPreferences(StrictBody):
    gender: Literal["no_preference", "female", "male", "nonbinary"] = "no_preference"
    nationality: str = Field(default="No preference", min_length=1, max_length=80)
    language: str = Field(default="English", min_length=1, max_length=80)
    experience: Literal["any", "3_plus", "5_plus", "10_plus"] = "any"
    specialty: Literal["general", "beginner", "strength", "mobility", "adapted_training"] = "general"
    preferred_at: datetime
    timezone: str = Field(min_length=1, max_length=80)


class PlanReviewBody(StrictBody):
    plan_id: str
    context_fingerprint: str = Field(min_length=64, max_length=64)
    question: str = Field(min_length=1, max_length=1200)
    share_with_coach: bool = False
    preferences: CoachPreferences
