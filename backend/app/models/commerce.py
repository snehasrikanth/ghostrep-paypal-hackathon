"""Additive PayPal-edition tables. Training and analysis rows remain unchanged."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.entities import _utcnow, _uuid


class ServicePackage(Base):
    __tablename__ = "review_packages"
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    clip_count: Mapped[int] = mapped_column(Integer)
    deliverables_json: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReviewIntake(Base):
    __tablename__ = "review_intakes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(16))
    share_consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ai_consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recommendation_json: Mapped[str] = mapped_column(Text)
    shared_context_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_order_id: Mapped[str | None] = mapped_column(ForeignKey("review_orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ClipShare(Base):
    __tablename__ = "review_clip_shares"
    __table_args__ = (UniqueConstraint("intake_id", "recording_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    intake_id: Mapped[str] = mapped_column(ForeignKey("review_intakes.id"), index=True)
    recording_id: Mapped[str] = mapped_column(ForeignKey("recorded_sets.id"), index=True)
    consent_version: Mapped[str] = mapped_column(String(40), default="coach-sharing-2026-11-04")
    position: Mapped[int] = mapped_column(Integer, default=0)


class ReviewOrder(Base):
    __tablename__ = "review_orders"
    __table_args__ = (UniqueConstraint("user_id", "checkout_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    intake_id: Mapped[str] = mapped_column(ForeignKey("review_intakes.id"), unique=True)
    checkout_key: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16))
    package_json: Mapped[str] = mapped_column(Text)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    merchant_id: Mapped[str] = mapped_column(String(128))
    payment_state: Mapped[str] = mapped_column(String(32), default="created")
    provider_order_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    capture_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    approval_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_key: Mapped[str] = mapped_column(String(36), default=_uuid)
    capture_key: Mapped[str] = mapped_column(String(36), default=_uuid)
    create_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capture_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    schedule_anchor: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentHistory(Base):
    __tablename__ = "review_payment_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("review_orders.id"), index=True)
    state: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CoachTask(Base):
    __tablename__ = "review_coach_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("review_orders.id"), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    draft: Mapped[str] = mapped_column(Text, default="")
    draft_source: Mapped[str] = mapped_column(String(40), default="human")
    draft_revision: Mapped[int] = mapped_column(Integer, default=0)
    delivered_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_comparison: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CoachSession(Base):
    __tablename__ = "review_coach_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity: Mapped[str] = mapped_column(String(100))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReviewRefund(Base):
    __tablename__ = "review_refunds"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("review_orders.id"), unique=True)
    request_key: Mapped[str] = mapped_column(String(36), default=_uuid)
    amount_cents: Mapped[int] = mapped_column(Integer)
    provider_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    state: Mapped[str] = mapped_column(String(24), default="created")
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class WebhookEvent(Base):
    __tablename__ = "review_webhook_events"
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[str] = mapped_column(String(128))
    disposition: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CommerceMigration(Base):
    __tablename__ = "review_schema_versions"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CoachingCall(Base):
    __tablename__ = "review_coaching_calls"
    __table_args__ = (UniqueConstraint("order_id", "session_index"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("review_orders.id"), index=True)
    session_index: Mapped[int] = mapped_column(Integer)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="requested")
    requested_timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    change_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_timezone: Mapped[str | None] = mapped_column(String(80), nullable=True)


class CoachConversation(Base):
    __tablename__ = "coach_conversations"
    set_id: Mapped[str] = mapped_column(ForeignKey("recorded_sets.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    turns_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
