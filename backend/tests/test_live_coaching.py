"""Live coaching plans: price snapshots, consented scope and authorized scheduling."""
from datetime import timedelta

from fastapi.testclient import TestClient

from tests.test_commerce import shop, intake, coach, HEADERS
from app.models.commerce import ServicePackage, CoachingCall, ReviewOrder
from app.services.commerce.catalog import migrate_commerce
from app.services.commerce.orders import now


def live_order(shop, package_id="month-coaching", capture=True):
    with shop[2]() as db:
        for p in db.query(ServicePackage):
            p.active = p.id in {"day-coaching", "month-coaching"}
        db.commit()
    iid = intake(shop, budget_cents=None).json()["id"]
    r = shop[0].post("/reviews/orders", json={"intake_id": iid, "package_id": package_id, "checkout_key": iid})
    assert r.status_code == 200, r.text
    order = r.json()
    if capture:
        shop[1].orders[order["provider_order_id"]]["status"] = "APPROVED"
        r = shop[0].post(f"/reviews/orders/{order['id']}/capture", json={})
        assert r.status_code == 200, r.text
        order = r.json()
    return order


def request(shop, order):
    start = (now() + timedelta(days=3)).replace(second=0, microsecond=0).isoformat()
    r = shop[0].post(f"/reviews/orders/{order['id']}/calls", json={"starts_at": start})
    assert r.status_code == 200, r.text
    return r.json()


def test_live_catalog_migration_and_old_receipts_preserved(shop):
    order = live_order(shop, "day-coaching")
    assert order["amount_cents"] == 1500
    assert order["package"]["session_count"] == 1
    assert order["package"]["session_minutes"] == 20
    with shop[2]() as db:
        db.get(ServicePackage, "day-coaching").price_cents = 1800
        db.commit()
        migrate_commerce(db.get_bind())
        assert db.get(ServicePackage, "day-coaching").price_cents == 1800
    saved = shop[0].get(f"/reviews/orders/{order['id']}").json()
    assert saved["amount_cents"] == 1500


def test_month_plan_requests_four_calls_exactly_once(shop):
    order = live_order(shop)
    assert order["amount_cents"] == 7900
    assert order["package"]["session_minutes"] == 30
    scheduled = request(shop, order)
    assert len(scheduled["calls"]) == 4
    assert [c["session_index"] for c in scheduled["calls"]] == [1,2,3,4]
    assert all(c["status"] == "requested" and not c["meeting_url"] for c in scheduled["calls"])
    repeated = request(shop, order)
    assert [c["id"] for c in repeated["calls"]] == [c["id"] for c in scheduled["calls"]]


def test_schedule_requires_payment_and_owned_order(shop):
    order = live_order(shop, capture=False)
    body = {"starts_at": (now()+timedelta(days=3)).isoformat()}
    assert shop[0].post(f"/reviews/orders/{order['id']}/calls", json=body).status_code == 409
    bob = TestClient(shop[5], headers=HEADERS)
    assert bob.post(f"/reviews/orders/{order['id']}/calls", json=body).status_code == 404
    bob.close()


def test_only_coach_can_confirm_with_valid_meeting_link(shop):
    order = request(shop, live_order(shop))
    call = order["calls"][0]
    path = f"/coach/tasks/{order['task']['id']}/calls/{call['id']}/confirm"
    body = {"starts_at": call["requested_at"], "meeting_url": "https://meet.google.com/abc-defg-hij"}
    assert shop[0].post(path, json=body).status_code == 401
    coach(shop)
    for invalid in ["javascript:alert(1)", "https://evil.example/room", "https://zoom.us:123/call", "https://zoom.us:bad/call", "https://user:pass@zoom.us/call"]:
        assert shop[0].post(path, json={**body,"meeting_url":invalid}).status_code == 422
    r = shop[0].post(path, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["calls"][0]["status"] == "confirmed"
    assert r.json()["calls"][0]["meeting_url"] == body["meeting_url"]
    assert shop[0].post(f"/reviews/orders/{order['id']}/calls", json={"starts_at":body["starts_at"]}).status_code == 409
    assert shop[0].post(path.replace("confirm","complete"), json={}).status_code == 409


def test_scheduling_limits_refund_pause_and_overlap(shop):
    order = request(shop, live_order(shop))
    endpoint = f"/reviews/orders/{order['id']}/calls"
    for when in [now()-timedelta(days=1),now()+timedelta(minutes=10),now()+timedelta(days=100)]:
        assert shop[0].post(endpoint,json={"starts_at":when.isoformat()}).status_code == 422
    assert shop[0].post(endpoint,json={"starts_at":"2026-12-01T12:00:00"}).status_code == 422
    coach(shop)
    call = order["calls"][0]
    path = f"/coach/tasks/{order['task']['id']}/calls/{call['id']}/confirm"
    body = {"starts_at": call["requested_at"], "meeting_url":"https://meet.google.com/abc-defg-hij"}
    assert shop[0].post(path,json={**body,"starts_at":(now()+timedelta(days=50)).isoformat()}).status_code == 422
    assert shop[0].post(path,json=body).status_code == 200
    second = order["calls"][1]
    assert shop[0].post(path.replace(call["id"],second["id"]),json=body).status_code == 409
    with shop[2]() as db:
        db.get(ReviewOrder,order["id"]).payment_state="refund_pending"
        db.commit()
    paused=shop[0].get(f"/reviews/orders/{order['id']}").json()
    assert all(c["status"]=="paused" and c["meeting_url"] is None for c in paused["calls"])
    assert shop[0].post(path,json=body).status_code == 409


def test_month_cannot_bypass_server_budget_or_clip_ownership(shop):
    live_order(shop,"day-coaching")
    iid=intake(shop,budget_cents=2000).json()["id"]
    assert shop[0].post("/reviews/orders",json={"intake_id":iid,"package_id":"month-coaching","checkout_key":iid}).status_code==422
