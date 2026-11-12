import json

from sqlalchemy.dialects.sqlite import insert
from app.models.commerce import CommerceMigration, ServicePackage

LEGACY_PACKAGES = [
    {"id": "single-set", "name": "Single-set review", "price_cents": 1500, "clip_count": 1,
     "description": "One squat clip, one focused question, a coach-reviewed written response.",
     "deliverables": ["Review of one selected squat clip", "Written observations with available rep references", "One practical next-session suggestion"]},
    {"id": "two-clip", "name": "Two-clip comparison", "price_cents": 2500, "clip_count": 2,
     "description": "Two squat clips, one focused question, a coach-reviewed written comparison.",
     "deliverables": ["Review of two selected squat clips", "Written comparison grounded in available evidence", "One practical next-session suggestion"]},
]


PACKAGES = [
    {"id": "day-coaching", "name": "One-day coaching", "price_cents": 1500, "clip_count": 2,
     "description": "One scheduled 20-minute video call on a chosen day.",
     "deliverables": ["One 20-minute video call on a chosen day", "Talk through your shared squat clip and question", "Request a time after payment; your coach confirms availability", "One-time payment. No automatic renewal."]},
    {"id": "month-coaching", "name": "One-month coaching", "price_cents": 7900, "clip_count": 2,
     "description": "Four scheduled 30-minute video calls, approximately weekly over one month.",
     "deliverables": ["Four 30-minute video calls over one month", "Approximately weekly, with each time confirmed by your coach", "Talk through your shared squat clips and questions", "One-time payment. No automatic renewal."]},
    {"id": "additional-session", "name": "Additional instructor session", "price_cents": 1500, "clip_count": 2,
     "description": "One additional scheduled 20-minute session after a call or delivered instructor notes.",
     "deliverables": ["One additional 20-minute video call", "Your instructor can review, correct or disagree with the saved suggestion", "Request a time after payment; your instructor confirms availability", "Separate one-time purchase. No automatic renewal."]},
]

# Demo agentic fitness-commerce catalog. Server prices are authoritative.
AGENTIC_PACKAGES = [
    {"id": "ai-technique-review", "name": "AI Technique Review", "price_cents": 499, "clip_count": 1,
     "description": "Automated technique report assembled from saved movement analysis and rep comparisons.",
     "deliverables": ["Saved analysis and rep-linked comparisons in one report", "Practical replay and next-set review prompts",
                      "Automated assembly · no new AI inference or live coach review", "Unlocked only after confirmed payment"]},
    {"id": "expert-video-review", "name": "Expert Video Review", "price_cents": 1499, "clip_count": 1,
     "description": "Coach review request linked to your selected workout evidence and question.",
     "deliverables": ["Expert review request queued for a coach (demo workflow)", "Linked workout analysis and shared question",
                      "Independent feedback appears after a coach reviews and approves it", "One-time demo purchase · no automatic renewal"]},
    {"id": "personal-coaching-session", "name": "Personal Coaching Session", "price_cents": 2999, "clip_count": 1,
     "description": "30-minute coaching session booking request after verified payment.",
     "deliverables": ["30-minute session booking request (pending confirmation)", "Demo coaching workflow · no real coach is hired automatically",
                      "Preferred time requires coach confirmation", "One-time demo purchase · no automatic renewal"]},
]


def migrate_commerce(engine):
    """Add live-call plans once; retain old packages and immutable purchase snapshots."""
    from sqlalchemy import select, update
    with engine.begin() as conn:
        for p in LEGACY_PACKAGES + PACKAGES + AGENTIC_PACKAGES:
            values = {k: v for k, v in p.items() if k != "deliverables"}
            active = p in PACKAGES or p in AGENTIC_PACKAGES
            conn.execute(insert(ServicePackage).values(**values, currency="USD", active=active,
                         deliverables_json=json.dumps(p["deliverables"])).on_conflict_do_nothing())
        conn.execute(insert(CommerceMigration).values(version=1).on_conflict_do_nothing())
        if conn.execute(select(CommerceMigration.version).where(CommerceMigration.version == 2)).first() is None:
            conn.execute(update(ServicePackage).where(ServicePackage.id.in_([p["id"] for p in LEGACY_PACKAGES])).values(active=False))
            conn.execute(insert(CommerceMigration).values(version=2))
        # v3 adds scheduling metadata in place. Never rewrite a purchase snapshot.
        additions = {"review_intakes": {"shared_context_json": "TEXT", "previous_order_id": "TEXT"},
                     "review_coach_tasks": {"assessment": "TEXT", "ai_comparison": "TEXT", "next_steps": "TEXT"},
                     "review_clip_shares": {"position": "INTEGER NOT NULL DEFAULT 0"}, "review_orders": {"schedule_anchor": "DATETIME"}, "review_coaching_calls": {
            "requested_timezone": "TEXT NOT NULL DEFAULT 'UTC'", "change_requested_at": "DATETIME", "change_timezone": "TEXT"}}
        for table, fields in additions.items():
            names = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, ddl in fields.items():
                if name not in names:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        if conn.execute(select(CommerceMigration.version).where(CommerceMigration.version == 3)).first() is None:
            for p in PACKAGES:
                conn.execute(update(ServicePackage).where(ServicePackage.id == p["id"]).values(
                    name=p["name"], description=p["description"], price_cents=p["price_cents"], deliverables_json=json.dumps(p["deliverables"])))
            conn.execute(insert(CommerceMigration).values(version=3))
        conn.execute(insert(CommerceMigration).values(version=4).on_conflict_do_nothing())
        conn.execute(insert(CommerceMigration).values(version=5).on_conflict_do_nothing())
        # v6: agentic fitness-commerce catalog. Preserve purchased snapshots and instructor offers.
        if conn.execute(select(CommerceMigration.version).where(CommerceMigration.version == 6)).first() is None:
            for p in AGENTIC_PACKAGES:
                values = {k: v for k, v in p.items() if k != "deliverables"}
                conn.execute(insert(ServicePackage).values(**values, currency="USD", active=True,
                             deliverables_json=json.dumps(p["deliverables"])).on_conflict_do_nothing())
                conn.execute(update(ServicePackage).where(ServicePackage.id == p["id"]).values(
                    name=p["name"], description=p["description"], price_cents=p["price_cents"],
                    clip_count=p["clip_count"], active=True, deliverables_json=json.dumps(p["deliverables"])))
            conn.execute(insert(CommerceMigration).values(version=6))
        # v7 corrects service descriptions without changing historical purchased terms or prices.
        if conn.execute(select(CommerceMigration.version).where(CommerceMigration.version == 7)).first() is None:
            for p in AGENTIC_PACKAGES:
                conn.execute(update(ServicePackage).where(ServicePackage.id == p["id"]).values(
                    description=p["description"], deliverables_json=json.dumps(p["deliverables"])))
            conn.execute(insert(CommerceMigration).values(version=7))


def _meta(package_id: str) -> dict:
    if package_id == "ai-technique-review":
        return {"family": "agentic", "kind": "ai_report", "min_clips": 1, "session_count": 0, "session_minutes": 0,
                "human_delivery": False, "label": "Automated report from saved analysis"}
    if package_id == "expert-video-review":
        return {"family": "agentic", "kind": "written_review", "min_clips": 1, "session_count": 0, "session_minutes": 0,
                "human_delivery": True, "label": "Expert review request · pending coach delivery"}
    if package_id == "personal-coaching-session":
        return {"family": "agentic", "kind": "live_calls", "min_clips": 1, "session_count": 1, "session_minutes": 30,
                "human_delivery": True, "label": "Demo booking request · pending confirmation"}
    if package_id in {"day-coaching", "month-coaching", "additional-session"}:
        return {"family": "instructor", "kind": "live_calls",
                "min_clips": 1,
                "session_count": 4 if package_id == "month-coaching" else 1,
                "session_minutes": 30 if package_id == "month-coaching" else 20,
                "human_delivery": True, "label": "Instructor video coaching"}
    return {"family": "legacy", "kind": "written_review", "min_clips": None, "session_count": 0, "session_minutes": 0,
            "human_delivery": True, "label": "Written coach review"}


def package_out(p):
    meta = _meta(p.id)
    min_clips = meta["min_clips"] if meta["min_clips"] is not None else p.clip_count
    return {"id": p.id, "name": p.name, "description": p.description, "price_cents": p.price_cents,
            "currency": p.currency, "clip_count": p.clip_count, "deliverables": json.loads(p.deliverables_json),
            "exercise": "barbell_squat", "active": p.active, "kind": meta["kind"], "family": meta["family"],
            "human_delivery": meta["human_delivery"], "delivery_label": meta["label"],
            "min_clips": min_clips,
            "session_count": meta["session_count"], "session_minutes": meta["session_minutes"]}


def configured_package(p, settings):
    result = package_out(p)
    setting = {"day-coaching": "coaching_session_price_cents", "month-coaching": "coaching_month_price_cents",
               "additional-session": "coaching_additional_price_cents"}.get(p.id)
    if setting:
        price = getattr(settings, setting)
        result["active"] = bool(p.active and settings.coaching_prices_approved and price is not None)
        result["price_cents"] = price if price is not None else 0
    # Agentic catalog prices are server-owned demo amounts; never accept browser/AI amounts.
    return result


def active_packages(db, settings, *, include_additional=False, family: str | None = None):
    result = [configured_package(p, settings) for p in db.query(ServicePackage).filter_by(active=True, currency="USD")]
    packages = [p for p in result if p["active"] and (include_additional or p["id"] != "additional-session")]
    if family:
        packages = [p for p in packages if p.get("family") == family]
    return sorted(packages, key=lambda p: (p["price_cents"], p["id"]))


def matches_clips(package, count):
    return package.get("min_clips", package["clip_count"]) <= count <= package["clip_count"]
