"""Agentic fitness-commerce flow: recommend → approve → capture → fulfill."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import settings_dep
from app.api.routes.payments import provider_dep as payments_provider_dep
from app.api.routes.reviews import provider_dep as reviews_provider_dep
from app.config import get_settings
from app.database import Base, get_db
from app.models.commerce import CoachTask, ServicePackage
from app.models.entities import RecordedSet, UserSession, WorkoutSession
from app.services.commerce.catalog import migrate_commerce
from tests.test_commerce import HEADERS, FakeSandbox


@pytest.fixture
def agentic(tmp_path, monkeypatch):
    import app.main as main_module
    import app.services.commerce.auth as coach_auth
    from app.main import create_app

    monkeypatch.setattr(coach_auth, "_attempts", {})
    settings = get_settings().model_copy(update={
        "paypal_client_id": "fake-client", "paypal_client_secret": "fake-secret",
        "paypal_merchant_id": "MERCHANT", "paypal_webhook_id": "WEBHOOK",
        "enable_meta_api": False, "app_env": "development", "commerce_simulator_enabled": True,
        "coaching_prices_approved": True, "coaching_session_price_cents": 1500,
        "coaching_month_price_cents": 7900, "coaching_additional_price_cents": 1500,
    })
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    engine = create_engine(f"sqlite:///{tmp_path / 'agentic.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    migrate_commerce(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        for package in db.query(ServicePackage):
            package.active = package.id in {
                "ai-technique-review", "expert-video-review", "personal-coaching-session",
            }
        db.commit()

    def db_dep():
        with factory() as db:
            yield db

    provider = FakeSandbox(settings)
    app = create_app()
    app.dependency_overrides.update({
        get_db: db_dep,
        settings_dep: lambda: settings,
        reviews_provider_dep: lambda: provider.provider,
        payments_provider_dep: lambda: provider.provider,
    })
    client = TestClient(app, headers=HEADERS)
    client.get("/api/payments/recordings")
    with factory() as db:
        token = client.cookies[settings.session_cookie]
        uid = db.query(UserSession).filter_by(token=token).one().user_id
        session = WorkoutSession(user_id=uid)
        db.add(session); db.flush()
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"private-video-fixture")
        own = RecordedSet(
            user_id=uid, session_id=session.id, exercise_id="barbell_squat", entry_source="video",
            processing_status="SAVED", analysis_requested=False, normalized_path=str(path),
            duration_seconds=12, set_index=1,
        )
        demo = RecordedSet(
            user_id=uid, session_id=session.id, exercise_id="barbell_squat", entry_source="demo",
            processing_status="SAVED", analysis_requested=False, normalized_path=str(path),
            duration_seconds=12, set_index=2, original_filename="DEMO_FIXTURE",
        )
        db.add_all([own, demo]); db.commit()
        ids = {"own": own.id, "demo": demo.id}
    yield client, provider, factory, settings, ids, app
    client.close(); engine.dispose()


def recommend(agentic, *, recording="own", **overrides):
    client, _, _, _, ids, _ = agentic
    body = {
        "question": "My later reps show torso lean and less stability. What coaching helps?",
        "recording_ids": [ids[recording]], "share_with_coach": True, "mode": "sandbox", "budget_cents": 3000,
    }
    body.update(overrides)
    return client.post("/api/payments/recommendations", json=body)


def pay(agentic, package_id="ai-technique-review", *, recording="own", mode="sandbox"):
    client, provider, _, _, _, _ = agentic
    intake = recommend(agentic, recording=recording, mode=mode).json()
    response = client.post("/api/payments/orders", json={
        "intake_id": intake["id"], "package_id": package_id,
        "checkout_key": intake["id"] + "-checkout", "approved": True,
    })
    assert response.status_code == 200, response.text
    order = response.json()
    if mode == "sandbox":
        provider.orders[order["provider_order_id"]]["status"] = "APPROVED"
    return order


def test_agentic_catalog_prices_are_server_owned(agentic):
    catalog = agentic[0].get("/api/payments/catalog").json()["packages"]
    by_id = {p["id"]: p for p in catalog}
    assert by_id["ai-technique-review"]["price_cents"] == 499
    assert by_id["expert-video-review"]["price_cents"] == 1499
    assert by_id["personal-coaching-session"]["price_cents"] == 2999
    assert all(p["family"] == "agentic" for p in catalog)


def test_recommendation_uses_movement_signals_and_budget(agentic):
    mild = recommend(agentic, budget_cents=500).json()["recommendation"]
    assert mild["outcome"] == "no_match"
    assert mild["package_id"] is None
    assert mild["analysis"]["beneficial"] is False
    assert "alternatives" in mild
    blocked = recommend(agentic, question="Is this pain safe for my injury?").json()["recommendation"]
    assert blocked["outcome"] == "no_match"
    tight = recommend(agentic, budget_cents=100).json()["recommendation"]
    assert tight["outcome"] == "no_match"


def test_checkout_requires_explicit_approval(agentic):
    intake = recommend(agentic).json()
    denied = agentic[0].post("/api/payments/orders", json={
        "intake_id": intake["id"], "package_id": "ai-technique-review",
        "checkout_key": intake["id"] + "-no", "approved": False,
    })
    assert denied.status_code == 422
    assert not agentic[1].posts


def test_browser_cannot_set_amount(agentic):
    intake = recommend(agentic).json()
    tampered = agentic[0].post("/api/payments/orders", json={
        "intake_id": intake["id"], "package_id": "ai-technique-review",
        "checkout_key": intake["id"] + "-amt", "approved": True, "amount_cents": 1,
    })
    assert tampered.status_code == 422


def test_ai_technique_unlocks_only_after_verified_capture(agentic):
    order = pay(agentic, "ai-technique-review")
    assert order["payment_state"] == "checkout_ready"
    assert order["task"] is None
    captured = agentic[0].post(f"/api/payments/orders/{order['id']}/capture", json={})
    assert captured.status_code == 200, captured.text
    body = captured.json()
    assert body["payment_state"] == "paid"
    assert body["amount_cents"] == 499
    assert body["task"]["status"] == "delivered"
    assert "AI Technique Review" in (body["task"]["delivered_text"] or "")
    assert "automated" in (body["task"]["author"] or "").lower()
    assert "No new model call" in body["task"]["delivered_text"]
    assert body["followup_available"] is False
    again = agentic[0].post(f"/api/payments/orders/{order['id']}/capture", json={}).json()
    assert again["task"]["status"] == "delivered"
    with agentic[2]() as db:
        assert db.query(CoachTask).filter_by(order_id=order["id"]).count() == 1


def test_expert_and_session_fulfillment_are_pending_human(agentic):
    expert = pay(agentic, "expert-video-review")
    expert_paid = agentic[0].post(f"/api/payments/orders/{expert['id']}/capture", json={}).json()
    assert expert_paid["payment_state"] == "paid"
    assert expert_paid["task"]["status"] == "queued"
    assert expert_paid["fulfillment"]["human_delivery"] is True

    session = pay(agentic, "personal-coaching-session")
    session_paid = agentic[0].post(f"/api/payments/orders/{session['id']}/capture", json={}).json()
    assert session_paid["package"]["session_minutes"] == 30
    assert session_paid["task"]["status"] == "queued"
    assert "pending" in (session_paid["task"]["assessment"] or "").lower()


def test_unauthorized_order_access_and_cancel(agentic):
    order = pay(agentic)
    bob = TestClient(agentic[5], headers=HEADERS)
    assert bob.get(f"/api/payments/orders/{order['id']}").status_code == 404
    assert bob.post(f"/api/payments/orders/{order['id']}/capture", json={}).status_code == 404
    canceled = agentic[0].post(f"/api/payments/orders/{order['id']}/cancel", json={}).json()
    assert canceled["payment_state"] == "canceled"


def test_simulated_payment_and_history(agentic, monkeypatch):
    client, _, factory, _, ids, _ = agentic
    from app.models.entities import RecordedSet
    import app.services.commerce.orders as orders_mod
    with factory() as db:
        monkeypatch.setattr(orders_mod, "DEMO_USER_ID", db.get(RecordedSet, ids["demo"]).user_id)
    intake = recommend(agentic, recording="demo", mode="simulated").json()
    order = client.post("/api/payments/orders", json={
        "intake_id": intake["id"], "package_id": "ai-technique-review",
        "checkout_key": intake["id"] + "-sim", "approved": True,
    }).json()
    assert order["mode"] == "simulated"
    paid = client.post(f"/api/payments/orders/{order['id']}/simulate", json={"result": "completed"}).json()
    assert paid["payment_state"] == "paid"
    assert paid["task"]["status"] == "delivered"
    history = client.get("/api/payments/orders").json()
    assert any(o["id"] == order["id"] for o in history)


def test_payment_config_never_returns_secret(agentic):
    cfg = agentic[0].get("/api/payments/config").json()
    assert cfg["sandbox"] is True
    assert cfg["client_id"] == "fake-client"
    assert cfg["client_token"] is None
    assert not agentic[1].posts
    raw = json.dumps(cfg)
    assert "fake-secret" not in raw
    assert "fake-private-access-token" not in raw


def test_duplicate_capture_does_not_double_charge(agentic):
    order = pay(agentic)
    first = agentic[0].post(f"/api/payments/orders/{order['id']}/capture", json={})
    assert first.status_code == 200
    posts_before = len(agentic[1].posts)
    second = agentic[0].post(f"/api/payments/orders/{order['id']}/capture", json={})
    assert second.status_code == 200
    assert second.json()["payment_state"] == "paid"
    # Second attempt reconciles; it must not create a new capture POST after paid.
    capture_posts = [p for p in agentic[1].posts[posts_before:] if p[0].endswith("/capture")]
    assert capture_posts == []


def plan_review_request(agentic):
    from datetime import datetime, timedelta, timezone
    from app.models.entities import WorkoutPlan, Profile
    client, _, factory, settings, _, _ = agentic
    with factory() as db:
        uid = db.query(UserSession).filter_by(token=client.cookies[settings.session_cookie]).one().user_id
        plan = WorkoutPlan(user_id=uid, name="Generated strength week", duration_minutes=40, source="meta_live")
        db.add(plan)
        db.add(Profile(user_id=uid, goal="strength", experience="beginner", days_per_week=3,
                       session_duration_minutes=40, equipment_json='["dumbbells"]', limitations_json='["Avoid deep knee flexion"]'))
        db.commit(); pid = plan.id
    preview = client.get(f"/api/payments/plan-reviews/{pid}")
    assert preview.status_code == 200, preview.text
    return {"plan_id": pid, "question": "Please verify the plan against my restrictions.", "share_with_coach": True,
            "context_fingerprint": preview.json()["fingerprint"],
            "preferences": {"gender": "female", "nationality": "Indian", "language": "English", "experience": "5_plus",
                            "specialty": "adapted_training", "preferred_at": (datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
                            "timezone": "America/New_York"}}


def test_plan_review_without_recording_preserves_context_and_capture_gate(agentic):
    from app.models.commerce import CoachingCall
    from app.models.entities import WorkoutPlan
    client, provider, factory, _, _, _ = agentic
    body = plan_review_request(agentic)
    response = client.post("/api/payments/plan-reviews", json=body)
    assert response.status_code == 200, response.text
    intake = response.json()
    checkout = {"intake_id": intake["id"], "package_id": "personal-coaching-session", "checkout_key": intake["id"], "approved": True}
    response = client.post("/api/payments/orders", json=checkout)
    assert response.status_code == 200, response.text
    order = response.json()
    assert order["amount_cents"] == 2999 and not order["sharing"]["recording_ids"]
    assert order["task"] is None and order["calls"] == [] and order["shared_context"] is None
    with factory() as db:
        plan = db.get(WorkoutPlan, body["plan_id"]); plan.name = "Later edit"; db.commit()
    provider.orders[order["provider_order_id"]]["status"] = "APPROVED"
    paid = client.post(f"/api/payments/orders/{order['id']}/capture", json={})
    assert paid.status_code == 200, paid.text
    result = paid.json()
    assert result["payment_state"] == "paid" and result["task"]["status"] == "queued"
    assert result["plan_review"]["plan"]["name"] == "Generated strength week"
    assert result["plan_review"]["restrictions"] == ["Avoid deep knee flexion"]
    assert result["plan_review"]["preferences"]["gender"] == "female"
    assert len(result["calls"]) == 1 and result["calls"][0]["status"] == "requested"
    assert result["calls"][0]["session_index"] == 1
    client.post(f"/api/payments/orders/{order['id']}/capture", json={})
    with factory() as db:
        assert db.query(CoachingCall).filter_by(order_id=order["id"]).count() == 1


def test_plan_review_requires_consent_ownership_and_fixed_service(agentic):
    client = agentic[0]
    body = plan_review_request(agentic)
    assert client.post("/api/payments/plan-reviews", json={**body, "share_with_coach": False}).status_code == 422
    assert client.post("/api/payments/plan-reviews", json={**body, "plan_id": "missing"}).status_code == 404
    assert client.post("/api/payments/plan-reviews", json={**body, "context_fingerprint": "0"*64}).status_code == 409
    intake = client.post("/api/payments/plan-reviews", json=body).json()
    checkout = {"intake_id": intake["id"], "package_id": "ai-technique-review", "checkout_key": intake["id"], "approved": True}
    assert client.post("/api/payments/orders", json=checkout).status_code == 422
    assert client.post("/api/payments/orders", json={**checkout, "package_id": "personal-coaching-session", "approved": False}).status_code == 422
    assert client.post("/api/payments/plan-reviews", json={**body, "amount_cents": 1}).status_code == 422
    prefs = body["preferences"]
    assert client.post("/api/payments/plan-reviews", json={**body, "preferences": {**prefs, "timezone": "Invalid/Zone"}}).status_code == 422
    assert client.post("/api/payments/plan-reviews", json={**body, "preferences": {**prefs, "preferred_at": "2020-01-01T00:00:00Z"}}).status_code == 422
    client.cookies.clear()
    assert client.get(f"/api/payments/plan-reviews/{body['plan_id']}").status_code == 404


def test_recommendations_do_not_turn_generic_or_unreliable_text_into_technique_problems():
    from app.services.commerce.agentic import analyze_movement
    for facts in [
        {"limits": {"text": "Torso, depth, stability and similarity do not establish correct technique.", "evidence_ids": []}},
        {"rep_6": {"text": "Rep 6 measurements are not verified for comparison.", "evidence_ids": ["r6"]}},
        {"rep_6_torso_inclination": {"text": "unlinked claim", "evidence_ids": ["missing"]}},
    ]:
        result = analyze_movement([{"recording_id": "clip", "facts": facts, "evidence": {"r6": {"rep_id": 6, "seconds": 9}}}])
        assert result["beneficial"] is False
        assert result["severity"] == 0 and result["findings"] == []
    supported = {"recording_id": "clip", "facts": {
        "rep_5_torso_inclination": {"text": "Rep 5 torso angle differs from the reference.", "evidence_ids": ["r5"]},
        "rep_6_ascent_duration": {"text": "Rep 6 ascent took longer than the reference.", "evidence_ids": ["r6"]},
    }, "evidence": {"r5": {"rep_id": 5, "seconds": 8}, "r6": {"rep_id": 6, "seconds": 10}}}
    result = analyze_movement([supported])
    assert result["beneficial"] is True and result["recurring"] is True
    assert {f["rep_id"] for f in result["findings"]} == {5, 6}
    assert "stability" not in result["summary"]
    assert analyze_movement([supported, supported])["severity"] == result["severity"]


def test_explicit_live_session_request_does_not_claim_an_unmeasured_problem(agentic):
    result = recommend(agentic, question="I would like a live coaching session.", budget_cents=3000).json()["recommendation"]
    assert result["package_id"] == "personal-coaching-session"
    assert result["analysis"]["beneficial"] is False
    assert "not a detected technique problem" in result["explanation"]


def test_plan_review_demo_mode_is_server_owned_and_disabled_in_production(agentic, monkeypatch):
    import app.services.commerce.plan_review as plans
    client, _, _, settings, _, _ = agentic
    body = plan_review_request(agentic)
    # Stand-in demo identity is explicit in this isolated database; no real journal is changed.
    with agentic[2]() as db:
        uid = db.query(UserSession).filter_by(token=client.cookies[settings.session_cookie]).one().user_id
    monkeypatch.setattr(plans, "DEMO_USER_ID", uid)
    preview = client.get(f"/api/payments/plan-reviews/{body['plan_id']}").json()
    assert preview["mode"] == "simulated"
    body["context_fingerprint"] = preview["fingerprint"]
    request = client.post("/api/payments/plan-reviews", json=body).json()
    assert request["mode"] == "simulated"
    response = client.post("/api/payments/orders", json={"intake_id": request["id"], "package_id": "personal-coaching-session", "checkout_key": request["id"], "approved": True})
    assert response.status_code == 200, response.text
    order = response.json()
    paid = client.post(f"/api/payments/orders/{order['id']}/simulate", json={"result": "completed"})
    assert paid.status_code == 200, paid.text
    assert paid.json()["payment_state"] == "paid"
    assert not agentic[1].posts
    monkeypatch.setattr(settings, "app_env", "production")
    assert client.get(f"/api/payments/plan-reviews/{body['plan_id']}").status_code == 403


def test_plan_review_coach_delivery_and_refund_revoke_shared_context(agentic, monkeypatch):
    from app.services.commerce.auth import password_hash
    client, provider, factory, settings, _, _ = agentic
    body = plan_review_request(agentic)
    intake = client.post("/api/payments/plan-reviews", json=body).json()
    created = client.post("/api/payments/orders", json={"intake_id": intake["id"], "package_id": "personal-coaching-session", "checkout_key": intake["id"], "approved": True}).json()
    provider.orders[created["provider_order_id"]]["status"] = "APPROVED"
    paid = client.post(f"/api/payments/orders/{created['id']}/capture", json={}).json()
    path = f"/coach/tasks/{paid['task']['id']}"
    assert client.get(path).status_code == 401
    monkeypatch.setattr(settings, "coach_password_hash", password_hash("isolated-test-coach-password"))
    assert client.post("/coach/login", json={"password": "isolated-test-coach-password"}).status_code == 200
    assert client.get(path).json()["plan_review"]["plan_id"] == body["plan_id"]
    outline = client.post(path + "/draft/generate", json={"ai_consent": False})
    assert outline.status_code == 200, outline.text
    task = outline.json()["task"]
    assert "Saved restrictions: Avoid deep knee flexion" in task["draft"]
    assert "no AI call" in task["draft_source"]
    assert client.post(path + "/deliver", json={"reviewed_and_approved": True, "revision": task["revision"]}).status_code == 422
    response = client.put(path + "/draft", json={"text": "Independent plan review notes.", "assessment": "Reviewed exercise selection and workload.", "ai_comparison": "Adjust the plan to the saved movement restriction.", "next_steps": "Discuss suitable substitutions before the session.", "revision": task["revision"]})
    assert response.status_code == 200, response.text
    task = response.json()["task"]
    # Reconciliation must preserve the coach's edits and a single appointment.
    client.post(f"/api/payments/orders/{paid['id']}/reconcile", json={})
    assert client.get(path).json()["task"]["draft"] == "Independent plan review notes."
    delivered = client.post(path + "/deliver", json={"reviewed_and_approved": True, "revision": task["revision"]})
    assert delivered.status_code == 200, delivered.text
    assert client.get(f"/api/payments/orders/{paid['id']}").json()["task"]["status"] == "delivered"
    refunded = client.post(path + "/refund", json={})
    assert refunded.status_code == 200, refunded.text
    assert refunded.json()["plan_review"] is None
    assert all(c["meeting_url"] is None for c in refunded.json()["calls"])
    receipt = client.get(f"/api/payments/orders/{paid['id']}").json()
    assert receipt["plan_review"]["plan_id"] == body["plan_id"]
    assert receipt["payment_state"] == "refunded"
    assert "Reviewed exercise selection" in receipt["task"]["delivered_text"]
