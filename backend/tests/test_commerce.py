"""Payment integrity and workflow tests. All provider traffic uses an HTTPX fake transport."""
import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import settings_dep
from app.api.routes.reviews import provider_dep
from app.config import get_settings
from app.database import Base, get_db
from app.models.commerce import CoachTask, ReviewOrder, ReviewRefund, ServicePackage, WebhookEvent
from app.models.entities import RecordedSet, User, UserSession, WorkoutSession
from app.services.commerce.auth import password_hash
from app.services.commerce.catalog import migrate_commerce
from app.services.commerce.orders import now
from app.services.commerce.paypal import PayPal

HEADERS = {"X-GhostRep-CSRF": "1"}
WEBHOOK_HEADERS = {"paypal-auth-algo": "SHA256withRSA", "paypal-cert-url": "https://api.sandbox.paypal.com/cert",
                   "paypal-transmission-id": "transmission", "paypal-transmission-sig": "valid",
                   "paypal-transmission-time": "2026-11-04T20:00:00Z"}


class FakeSandbox:
    def __init__(self, settings):
        self.orders, self.refunds, self.keys, self.posts = {}, {}, {}, []
        self.capture_status = "COMPLETED"
        self.refund_status = "COMPLETED"
        self.capture_timeout = self.create_timeout = self.refund_timeout = False
        self.capture_delay = 0
        self.provider = PayPal(settings, transport=httpx.MockTransport(self.handle))

    def handle(self, request):
        assert request.url.host == "api-m.sandbox.paypal.com"
        path = request.url.path
        method = request.method
        if path == "/v1/oauth2/token":
            # Access tokens stay server-side; browser client tokens are a separate grant shape.
            body = request.content.decode() if request.content else ""
            if "response_type=client_token" in body or "client_token" in body:
                return httpx.Response(200, json={"client_token": "fake-browser-client-token", "expires_in": 3600})
            return httpx.Response(200, json={"access_token": "fake-private-access-token"})
        if path.endswith("verify-webhook-signature"):
            data = json.loads(request.content)
            return httpx.Response(200, json={"verification_status": "SUCCESS" if data["transmission_sig"] == "valid" else "FAILURE"})
        if method == "POST":
            key = request.headers["PayPal-Request-Id"]
            self.posts.append((path, key))
            if key in self.keys:
                return httpx.Response(200, json=copy.deepcopy(self.keys[key]))
            data = json.loads(request.content)
            if path == "/v2/checkout/orders":
                oid = "PP-" + str(len(self.orders) + 1)
                result = {"id": oid, "intent": "CAPTURE", "status": "CREATED", "purchase_units": data["purchase_units"],
                          "links": [{"rel": "payer-action", "href": f"https://www.sandbox.paypal.com/checkoutnow?token={oid}"}]}
                self.orders[oid] = result
                self.keys[key] = copy.deepcopy(result)
                if self.create_timeout:
                    self.create_timeout = False
                    raise httpx.ReadTimeout("fake response loss")
            elif path.endswith("/capture"):
                time.sleep(self.capture_delay)
                oid = path.split("/")[-2]
                result = self.orders[oid]
                result["status"] = "COMPLETED"
                result["purchase_units"][0]["payments"] = {"captures": [{"id": "CAP-" + oid,
                    "status": self.capture_status, "amount": result["purchase_units"][0]["amount"], "final_capture": True}]}
                self.keys[key] = copy.deepcopy(result)
                if self.capture_timeout:
                    self.capture_timeout = False
                    raise httpx.ReadTimeout("fake response loss after capture")
            elif path.endswith("/refund"):
                cid = path.split("/")[-2]
                result = {"id": "REF-" + cid, "status": self.refund_status, "amount": data["amount"],
                          "links": [{"rel": "up", "href": f"https://api-m.sandbox.paypal.com/v2/payments/captures/{cid}"}]}
                self.refunds[result["id"]] = result
                self.keys[key] = copy.deepcopy(result)
                if self.refund_status == "COMPLETED":
                    self.orders[cid.removeprefix("CAP-")]["purchase_units"][0]["payments"]["captures"][0]["status"] = "REFUNDED"
                if self.refund_timeout:
                    self.refund_timeout = False
                    raise httpx.ReadTimeout("fake refund response loss")
            else:
                raise AssertionError(path)
            return httpx.Response(201, json=copy.deepcopy(result))
        if path.startswith("/v2/checkout/orders/"):
            return httpx.Response(200, json=copy.deepcopy(self.orders[path.split("/")[-1]]))
        if path.startswith("/v2/payments/captures/"):
            cid = path.split("/")[-1]
            oid = cid.removeprefix("CAP-")
            cap = copy.deepcopy(self.orders[oid]["purchase_units"][0]["payments"]["captures"][0])
            cap["supplementary_data"] = {"related_ids": {"order_id": oid}}
            return httpx.Response(200, json=cap)
        if path.startswith("/v2/payments/refunds/"):
            return httpx.Response(200, json=copy.deepcopy(self.refunds[path.split("/")[-1]]))
        raise AssertionError(path)


@pytest.fixture
def shop(tmp_path, monkeypatch):
    import app.services.commerce.auth as coach_auth
    monkeypatch.setattr(coach_auth, "_attempts", {})
    from app.main import create_app
    import app.main as main_module
    settings = get_settings().model_copy(update={"paypal_client_id": "fake-client", "paypal_client_secret": "fake-secret",
        "paypal_merchant_id": "MERCHANT", "paypal_webhook_id": "WEBHOOK", "enable_meta_api": False,
        "app_env": "development", "commerce_simulator_enabled": True, "coach_password_hash": password_hash("private-coach-password"),
        "coaching_prices_approved": True, "coaching_session_price_cents": 1500,
        "coaching_month_price_cents": 7900, "coaching_additional_price_cents": 1500})
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    engine = create_engine(f"sqlite:///{tmp_path / 'shop.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    migrate_commerce(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    # Historical review orders remain supported after the live-coaching migration.
    with factory() as db:
        for package in db.query(ServicePackage):
            package.active = package.id in {"single-set", "two-clip"}
        db.commit()
    def db_dep():
        with factory() as db:
            yield db
    provider = FakeSandbox(settings)
    app = create_app()
    app.dependency_overrides.update({get_db: db_dep, settings_dep: lambda: settings, provider_dep: lambda: provider.provider})
    client = TestClient(app, headers=HEADERS)
    client.get("/reviews/recordings")
    with factory() as db:
        token = client.cookies[settings.session_cookie]
        uid = db.query(UserSession).filter_by(token=token).one().user_id
        session = WorkoutSession(user_id=uid)
        db.add(session); db.flush()
        path = tmp_path / "clip.mp4"
        path.write_bytes(b"private-video-fixture")
        recordings = [RecordedSet(user_id=uid, session_id=session.id, exercise_id="barbell_squat", entry_source="video",
                      processing_status="SAVED", analysis_requested=False, normalized_path=str(path), duration_seconds=12, set_index=i + 1) for i in range(2)]
        db.add_all(recordings); db.commit()
        ids = [r.id for r in recordings]
    yield client, provider, factory, settings, ids, app
    client.close(); engine.dispose()


def intake(shop, **overrides):
    client, _, _, _, ids, _ = shop
    return client.post("/reviews/intakes", json={"question": "What should I focus on in these reps?", "recording_ids": [ids[0]],
        "budget_cents": 2000, "share_with_coach": True, **overrides})


def checkout(shop):
    client, provider, _, _, _, _ = shop
    iid = intake(shop).json()["id"]
    response = client.post("/reviews/orders", json={"intake_id": iid, "package_id": "single-set", "checkout_key": iid})
    assert response.status_code == 200, response.text
    order = response.json()
    provider.orders[order["provider_order_id"]]["status"] = "APPROVED"
    return order


def paid(shop):
    order = checkout(shop)
    response = shop[0].post(f"/reviews/orders/{order['id']}/capture", json={})
    assert response.status_code == 200, response.text
    return response.json()


def coach(shop):
    response = shop[0].post("/coach/login", json={"password": "private-coach-password"})
    assert response.status_code == 200


def event(shop, order, kind="PAYMENT.CAPTURE.COMPLETED", eid="event-1", signature="valid", amount="15.00"):
    rid = order.get("capture_id") or "CAP-" + order["provider_order_id"]
    resource = {"id": rid, "amount": {"currency_code": "USD", "value": amount},
                "supplementary_data": {"related_ids": {"order_id": order["provider_order_id"]}}}
    return shop[0].post("/reviews/paypal/webhook", json={"id": eid, "event_type": kind, "resource": resource},
                        headers={**WEBHOOK_HEADERS, "paypal-transmission-sig": signature})


def test_catalog_budget_clips_and_consent_are_deterministic(shop):
    assert intake(shop, budget_cents=1499).json()["recommendation"]["outcome"] == "no_match"
    assert intake(shop, budget_cents=1500).json()["recommendation"]["package_id"] == "single-set"
    assert intake(shop, budget_cents=15.0).status_code == 422
    assert intake(shop, share_with_coach=False).status_code == 422
    assert intake(shop, question="why").json()["recommendation"]["outcome"] == "follow_up"
    assert intake(shop, recording_ids=shop[4], budget_cents=2500).json()["recommendation"]["package_id"] == "two-clip"
    assert intake(shop, recording_ids=[shop[4][0]] * 2).status_code == 422
    with shop[2]() as db:
        rec = db.get(RecordedSet, shop[4][0]); rec.exercise_id = "bench_press"; db.commit()
    assert intake(shop).status_code == 422


@pytest.mark.parametrize("tamper", [{"amount_cents": 1}, {"currency": "EUR"}, {"merchant_id": "ATTACKER"}])
def test_browser_cannot_choose_money_or_merchant(shop, tamper):
    iid = intake(shop).json()["id"]
    r = shop[0].post("/reviews/orders", json={"intake_id": iid, "package_id": "single-set", "checkout_key": iid, **tamper})
    assert r.status_code == 422
    assert not shop[1].posts


def test_package_and_budget_revalidated_at_checkout(shop):
    iid = intake(shop, budget_cents=1499).json()["id"]
    base = {"intake_id": iid, "checkout_key": iid}
    assert shop[0].post("/reviews/orders", json={**base, "package_id": "invented"}).status_code == 422
    assert shop[0].post("/reviews/orders", json={**base, "package_id": "single-set"}).status_code == 422
    assert shop[0].post("/reviews/orders", json={**base, "package_id": "two-clip"}).status_code == 422


def test_ownership_covers_intake_order_video_and_capture(shop):
    order = checkout(shop)
    bob = TestClient(shop[5], headers=HEADERS)
    assert bob.get(f"/reviews/orders/{order['id']}").status_code == 404
    assert bob.get(f"/reviews/orders/{order['id']}/clips/{shop[4][0]}/media").status_code == 404
    assert bob.post(f"/reviews/orders/{order['id']}/capture", json={}).status_code == 404
    assert bob.post("/reviews/intakes", json={"question": "Review these please", "recording_ids": [shop[4][0]], "share_with_coach": True}).status_code == 404
    assert bob.get(f"/reviews/intakes/{order['sharing']['recording_ids'][0]}").status_code == 404


def test_coach_privilege_and_demo_separation(shop):
    order = paid(shop); tid = order["task"]["id"]
    assert shop[0].get("/coach/tasks").status_code == 401
    assert shop[0].get(f"/coach/tasks/{tid}/clips").status_code == 401
    assert shop[0].post("/coach/dev-login", json={}).status_code == 200
    assert shop[0].get("/coach/tasks").json() == []
    assert shop[0].get(f"/coach/tasks/{tid}").status_code == 404
    coach(shop)
    assert shop[0].get(f"/coach/tasks/{tid}/clips").status_code == 200
    assert shop[0].get(f"/coach/tasks/{tid}/clips/{shop[4][1]}/media").status_code == 404


def test_production_disables_simulation_and_dev_coach(shop):
    shop[3].app_env = "production"
    assert shop[0].post("/coach/dev-login", json={}).status_code == 404
    assert intake(shop, mode="simulated").status_code == 403


def test_csrf_enforcement_and_untrusted_origin(shop):
    c = TestClient(shop[5])
    assert c.post("/coach/login", json={"password": "anything"}).status_code == 403
    assert shop[0].post("/coach/login", json={"password": "anything"}, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert shop[0].post("/demo/enter", headers={"Origin": "null"}).status_code == 403


def test_capture_retry_and_catalog_snapshot(shop):
    order = checkout(shop)
    with shop[2]() as db:
        package = db.get(ServicePackage, "single-set"); package.price_cents = 9900; package.active = False; db.commit()
    for _ in range(2):
        r = shop[0].post(f"/reviews/orders/{order['id']}/capture", json={})
        assert r.status_code == 200 and r.json()["amount_cents"] == 1500
    assert len([p for p, _ in shop[1].posts if p.endswith("/capture")]) == 1
    with shop[2]() as db:
        assert db.query(CoachTask).count() == 1


@pytest.mark.parametrize("field,value", [("amount", {"currency_code": "USD", "value": "0.01"}),
    ("amount", {"currency_code": "EUR", "value": "15.00"}), ("payee", {"merchant_id": "OTHER"}), ("custom_id", "OTHER")])
def test_provider_amount_currency_merchant_and_identity_checked(shop, field, value):
    order = checkout(shop)
    shop[1].orders[order["provider_order_id"]]["purchase_units"][0][field] = value
    r = shop[0].post(f"/reviews/orders/{order['id']}/capture", json={})
    assert r.status_code == 503
    with shop[2]() as db:
        assert db.query(CoachTask).count() == 0


@pytest.mark.parametrize("status,expected", [("PENDING", "capture_pending"), ("DECLINED", "failed")])
def test_pending_or_failed_capture_does_not_release_task(shop, status, expected):
    shop[1].capture_status = status
    order = checkout(shop)
    r = shop[0].post(f"/reviews/orders/{order['id']}/capture", json={})
    # Failed capture is surfaced as uncertain until reconciliation confirms failure.
    if expected == "failed":
        assert r.status_code == 503
        r = shop[0].post(f"/reviews/orders/{order['id']}/reconcile", json={})
    assert r.json()["payment_state"] == expected
    assert r.json()["task"] is None


def test_cancel_does_not_capture_and_callback_is_not_payment(shop):
    order = checkout(shop)
    assert shop[0].get(f"/reviews/orders/{order['id']}?paypal=approved").json()["task"] is None
    assert shop[0].post(f"/reviews/orders/{order['id']}/cancel", json={}).json()["payment_state"] == "canceled"
    assert shop[0].post(f"/reviews/orders/{order['id']}/capture", json={}).status_code == 409
    assert not any(p.endswith("/capture") for p, _ in shop[1].posts)


def test_capture_timeout_recovers_without_second_charge(shop):
    order = checkout(shop); shop[1].capture_timeout = True
    assert shop[0].post(f"/reviews/orders/{order['id']}/capture", json={}).status_code == 503
    r = shop[0].post(f"/reviews/orders/{order['id']}/capture", json={})
    assert r.json()["payment_state"] == "paid"
    assert len([p for p, _ in shop[1].posts if p.endswith("/capture")]) == 1
    with shop[2]() as db:
        assert db.query(CoachTask).count() == 1


def test_create_timeout_uses_persisted_request_key(shop):
    shop[1].create_timeout = True
    iid = intake(shop).json()["id"]
    data = {"intake_id": iid, "package_id": "single-set", "checkout_key": iid}
    assert shop[0].post("/reviews/orders", json=data).status_code == 503
    order = shop[0].get("/reviews/orders").json()[0]
    recovered = shop[0].post(f"/reviews/orders/{order['id']}/reconcile", json={})
    assert recovered.status_code == 200 and recovered.json()["payment_state"] == "checkout_ready"
    keys = [k for p, k in shop[1].posts if p == "/v2/checkout/orders"]
    assert len(keys) == 2 and len(set(keys)) == 1 and len(shop[1].orders) == 1


def test_concurrent_captures_create_exactly_one_task(shop):
    order = checkout(shop); shop[1].capture_delay = .12
    def run():
        c = TestClient(shop[5], headers=HEADERS, cookies=shop[0].cookies)
        return c.post(f"/reviews/orders/{order['id']}/capture", json={}).status_code
    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda _: run(), range(2)))
    assert 200 in codes and all(c in {200, 409} for c in codes)
    with shop[2]() as db:
        assert db.query(CoachTask).count() == 1
    assert len([p for p, _ in shop[1].posts if p.endswith("/capture")]) == 1


def test_webhook_signature_deduplication_and_out_of_order(shop):
    order = paid(shop)
    assert event(shop, order, signature="invalid").status_code == 400
    assert event(shop, order).status_code == 200
    assert event(shop, order).json()["duplicate"] is True
    assert event(shop, order, kind="PAYMENT.CAPTURE.PENDING", eid="event-old").status_code == 200
    assert shop[0].get(f"/reviews/orders/{order['id']}").json()["payment_state"] == "paid"
    assert event(shop, order, eid="event-bad-amount", amount="1.00").status_code == 400
    with shop[2]() as db:
        assert db.query(CoachTask).count() == 1
        assert db.query(WebhookEvent).count() == 2


def test_webhook_can_recover_capture_before_browser_callback(shop):
    order = checkout(shop)
    local = None
    with shop[2]() as db:
        local = db.get(ReviewOrder, order["id"])
        shop[1].provider.capture(local)  # fake external result; browser never submits capture callback
    assert event(shop, order).status_code == 200
    receipt = shop[0].get(f"/reviews/orders/{order['id']}").json()
    assert receipt["payment_state"] == "paid" and receipt["task"]


def test_pending_capture_webhook_retains_identity_without_releasing_task(shop):
    order = checkout(shop)
    shop[1].capture_status = "PENDING"
    with shop[2]() as db:
        shop[1].provider.capture(db.get(ReviewOrder, order["id"]))
    assert event(shop, order, kind="PAYMENT.CAPTURE.PENDING", eid="pending-capture").status_code == 200
    receipt = shop[0].get(f"/reviews/orders/{order['id']}").json()
    assert receipt["payment_state"] == "capture_pending"
    assert receipt["capture_id"]
    assert receipt["task"] is None
    assert event(shop, order, kind="PAYMENT.CAPTURE.PENDING", eid="pending-capture").json()["duplicate"] is True


def test_draft_requires_human_approval_and_revision_before_delivery(shop):
    order = paid(shop); coach(shop); tid = order["task"]["id"]
    assert shop[0].post(f"/coach/tasks/{tid}/deliver", json={"revision": 0, "reviewed_and_approved": False}).status_code == 422
    generated = shop[0].post(f"/coach/tasks/{tid}/draft/generate", json={"ai_consent": False}).json()
    revision = generated["task"]["revision"]
    assert shop[0].get(f"/reviews/orders/{order['id']}").json()["task"].get("draft") is None
    assert shop[0].post(f"/coach/tasks/{tid}/deliver", json={"revision": revision, "reviewed_and_approved": True}).status_code == 422
    text = "Observations: I reviewed your saved clip. Recommendation: replay your selected set and practice one consistent setup next session."
    saved = shop[0].put(f"/coach/tasks/{tid}/draft", json={"text": text, "revision": revision}).json()
    assert shop[0].post(f"/coach/tasks/{tid}/deliver", json={"revision": revision, "reviewed_and_approved": True}).status_code == 422
    done = shop[0].post(f"/coach/tasks/{tid}/deliver", json={"revision": saved["task"]["revision"], "reviewed_and_approved": True})
    assert done.status_code == 200 and done.json()["task"]["delivered_text"] == text
    assert shop[0].put(f"/coach/tasks/{tid}/draft", json={"text": "replace feedback", "revision": 2}).status_code == 409


def test_refund_is_coach_only_full_idempotent_and_stops_delivery(shop):
    order = paid(shop); tid = order["task"]["id"]
    assert shop[0].post(f"/coach/tasks/{tid}/refund", json={}).status_code == 401
    coach(shop)
    for _ in range(2):
        r = shop[0].post(f"/coach/tasks/{tid}/refund", json={})
        assert r.status_code == 200 and r.json()["payment_state"] == "refunded"
    assert len([p for p, _ in shop[1].posts if p.endswith("/refund")]) == 1
    assert shop[0].get(f"/coach/tasks/{tid}/clips").status_code == 403
    assert shop[0].post(f"/coach/tasks/{tid}/deliver", json={"revision": 0, "reviewed_and_approved": True}).status_code == 409
    assert event(shop, order, eid="late-capture").status_code == 200
    assert shop[0].get(f"/reviews/orders/{order['id']}").json()["payment_state"] == "refunded"


def test_refund_timeout_reconciles_without_duplicate(shop):
    order = paid(shop); coach(shop); shop[1].refund_timeout = True; tid = order["task"]["id"]
    assert shop[0].post(f"/coach/tasks/{tid}/refund", json={}).status_code == 503
    recovered = shop[0].post(f"/coach/tasks/{tid}/refund", json={})
    assert recovered.json()["payment_state"] == "refunded"
    assert len([p for p, _ in shop[1].posts if p.endswith("/refund")]) == 1


def test_pending_and_failed_refund_never_claim_success(shop):
    order = paid(shop); coach(shop); shop[1].refund_status = "PENDING"; tid = order["task"]["id"]
    r = shop[0].post(f"/coach/tasks/{tid}/refund", json={})
    assert r.json()["payment_state"] == "refund_pending"
    shop[1].refunds[r.json()["refund"]["provider_id"]]["status"] = "FAILED"
    r = shop[0].post(f"/coach/tasks/{tid}/reconcile", json={})
    assert r.json()["payment_state"] == "paid" and r.json()["refund"]["state"] == "failed"


def test_migration_preserves_training_and_catalog_edits(shop):
    with shop[2]() as db:
        package = db.get(ServicePackage, "single-set"); package.price_cents = 1900; db.commit()
        migrate_commerce(db.get_bind())
        db.expire_all()
        assert db.get(ServicePackage, "single-set").price_cents == 1900
        assert db.get(RecordedSet, shop[4][0]).normalized_path


def test_recommendation_get_never_calls_provider_or_model(shop, monkeypatch):
    from app.services.meta.muse import MuseProvider
    monkeypatch.setattr(MuseProvider, "commerce_selection", lambda *a, **k: pytest.fail("Unexpected model call"))
    result = intake(shop).json()
    assert result["recommendation"]["source"] == "deterministic"
    for _ in range(2):
        assert shop[0].get(f"/reviews/intakes/{result['id']}").status_code == 200
    assert not shop[1].posts
