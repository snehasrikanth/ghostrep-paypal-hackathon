"""Consented snapshots, independent instructor advice and separately approved purchases."""
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models.commerce import CoachConversation, CoachTask, ReviewOrder, ServicePackage
from app.models.entities import RecordedSet
from tests.test_commerce import shop, coach, HEADERS
from tests.test_feedback_first import analyzed_fixture, ask
from tests.test_live_coaching import live_order


def synthetic_identity(shop, monkeypatch):
    # Isolated fixture actor stands in for the development athlete. Keep synthetic
    # recording provenance intact and use only the explicitly simulated transport.
    import app.services.commerce.orders as orders
    with shop[2]() as db:
        monkeypatch.setattr(orders, "DEMO_USER_ID", db.get(RecordedSet, shop[4][0]).user_id)


def preview_intake(shop, rid, **overrides):
    preview = shop[0].get(f"/reviews/recordings/{rid}/handoff-context")
    assert preview.status_code == 200, preview.text
    response = shop[0].post("/reviews/intakes", json={"question": "Please review the saved suggestion and this selected set.",
        "recording_ids": [rid], "share_with_coach": True, "share_ai_context": True,
        "context_fingerprint": preview.json()["fingerprint"], "mode": "simulated", **overrides})
    assert response.status_code == 200, response.text
    return response.json(), preview.json()["context"]


def buy(shop, intake, package="day-coaching"):
    result = shop[0].post("/reviews/orders", json={"intake_id": intake["id"], "package_id": package, "checkout_key": str(uuid4())})
    assert result.status_code == 200, result.text
    order = result.json()
    if order["mode"] == "simulated":
        paid = shop[0].post(f"/reviews/orders/{order['id']}/simulate", json={"result": "completed"})
    else:
        shop[1].orders[order["provider_order_id"]]["status"] = "APPROVED"
        paid = shop[0].post(f"/reviews/orders/{order['id']}/capture", json={})
    assert paid.status_code == 200, paid.text
    return paid.json()


def enable_calls(shop):
    with shop[2]() as db:
        for row in db.query(ServicePackage):
            row.active = row.id in {"day-coaching", "month-coaching", "additional-session"}
        db.commit()


def test_owner_approval_and_configured_prices_control_new_offers(shop, monkeypatch):
    enable_calls(shop)
    monkeypatch.setattr(shop[3], "coaching_prices_approved", False)
    assert shop[0].get("/reviews/catalog").json()["packages"] == []
    rid = shop[4][0]
    intake = shop[0].post("/reviews/intakes", json={"question": "Help me review this set.", "recording_ids": [rid], "share_with_coach": True}).json()
    assert shop[0].post("/reviews/orders", json={"intake_id": intake["id"], "package_id": "day-coaching", "checkout_key": str(uuid4())}).status_code == 422
    monkeypatch.setattr(shop[3], "coaching_prices_approved", True)
    monkeypatch.setattr(shop[3], "coaching_session_price_cents", 2300)
    order = buy(shop, intake)
    assert order["amount_cents"] == 2300
    assert shop[1].orders[order["provider_order_id"]]["purchase_units"][0]["amount"]["value"] == "23.00"
    monkeypatch.setattr(shop[3], "coaching_session_price_cents", 3100)
    assert shop[0].get(f"/reviews/orders/{order['id']}").json()["package"]["price_cents"] == 2300
    packages = shop[0].get("/reviews/catalog").json()["packages"]
    assert next(p for p in packages if p["id"] == "day-coaching")["price_cents"] == 3100


def test_handoff_is_exact_consent_bounded_and_immutable(shop, monkeypatch):
    synthetic_identity(shop, monkeypatch)
    enable_calls(shop)
    rid = analyzed_fixture(shop)
    ask(shop, rid, "Explain the whole set first.")
    ask(shop, rid, "What happened in rep 3?")
    intake, expected = preview_intake(shop, rid)
    assert expected["latest_answer"]["question"] == "What happened in rep 3?"
    assert "Explain the whole set first." not in json.dumps(expected)
    assert not shop[1].posts  # Opening context and consenting to saved text make no paid AI/payment calls.
    with shop[2]() as db:
        rec = db.get(RecordedSet, rid)
        rec.coaching.reason = "A later saved suggestion must not rewrite prior consent."
        db.get(CoachConversation, rid).turns_json = "[]"
        db.commit()
    order = buy(shop, intake)
    assert order["shared_context"] == expected
    assert order["sharing"]["ai_consented_at"] is None
    coach(shop)
    task_url = f"/coach/tasks/{order['task']['id']}"
    assert shop[0].get(task_url).json()["shared_context"] == expected
    for _ in range(2):
        assert shop[0].post(f"/reviews/orders/{order['id']}/simulate", json={"result": "completed"}).json()["task"]["id"] == order["task"]["id"]
    with shop[2]() as db:
        assert db.query(CoachTask).filter_by(order_id=order["id"]).count() == 1
    assert shop[0].post(task_url + "/refund", json={}).status_code == 200
    assert shop[0].get(task_url).json()["shared_context"] is None
    assert shop[0].get(f"/reviews/orders/{order['id']}").json()["shared_context"] == expected


def test_context_preview_requires_ownership_and_reconsent_after_changes(shop, monkeypatch):
    synthetic_identity(shop, monkeypatch)
    rid = analyzed_fixture(shop)
    preview = shop[0].get(f"/reviews/recordings/{rid}/handoff-context").json()
    with TestClient(shop[5], headers=HEADERS) as another:
        assert another.get(f"/reviews/recordings/{rid}/handoff-context").status_code == 404
        assert another.post("/reviews/intakes", json={"question": "Share this suggestion", "recording_ids": [rid], "share_with_coach": True, "share_ai_context": True, "context_fingerprint": preview["fingerprint"]}).status_code == 404
    ask(shop, rid)
    body = {"question": "Help with the shared suggestion", "recording_ids": [rid], "share_with_coach": True,
            "share_ai_context": True, "context_fingerprint": preview["fingerprint"], "mode": "simulated"}
    assert shop[0].post("/reviews/intakes", json=body).status_code == 409
    assert shop[0].post("/reviews/intakes", json={**body, "share_ai_context": False}).status_code == 422
    not_shared = shop[0].post("/reviews/intakes", json={**body, "share_ai_context": False, "context_fingerprint": None})
    assert not_shared.status_code == 200 and not_shared.json()["shared_context"] is None


def test_instructor_records_independent_assessment_before_delivery(shop, monkeypatch):
    synthetic_identity(shop, monkeypatch)
    enable_calls(shop)
    rid = analyzed_fixture(shop)
    intake, _ = preview_intake(shop, rid)
    order = buy(shop, intake)
    coach(shop)
    url = f"/coach/tasks/{order['task']['id']}"
    response = shop[0].put(url + "/draft", json={"text": "I simply approve whatever the AI suggested.", "revision": 0})
    assert response.status_code == 200
    assert shop[0].post(url + "/deliver", json={"revision": 1, "reviewed_and_approved": True}).status_code == 422
    fields = {"text": "", "revision": 1, "assessment": "I reviewed rep 3 and the available replay.",
              "ai_comparison": "I disagree with changing targets based on this example alone.",
              "next_steps": "Review the reference replay together before choosing a new focus."}
    assert shop[0].put(url + "/draft", json=fields).status_code == 200
    assert "assessment" not in shop[0].get(f"/reviews/orders/{order['id']}").json()["task"]
    result = shop[0].post(url + "/deliver", json={"revision": 2, "reviewed_and_approved": True})
    assert result.status_code == 200, result.text
    task = shop[0].get(f"/reviews/orders/{order['id']}").json()["task"]
    assert task["ai_comparison"] == fields["ai_comparison"]
    assert "Instructor assessment" in task["delivered_text"] and task["author"]
    assert shop[0].put(url + "/draft", json={**fields, "revision": 2}).status_code == 409


def test_additional_session_requires_owned_finished_support_and_new_purchase(shop, monkeypatch):
    first = live_order(shop, "day-coaching")
    enable_calls(shop)
    iid = shop[0].post("/reviews/intakes", json={"question": "I want another individual session.", "recording_ids": [shop[4][0]], "share_with_coach": True}).json()["id"]
    assert shop[0].post("/reviews/orders", json={"intake_id": iid, "package_id": "additional-session", "checkout_key": str(uuid4())}).status_code == 404
    body = {"question": "I want another individual session.", "recording_ids": [shop[4][0]], "share_with_coach": True, "previous_order_id": first["id"]}
    assert shop[0].post("/reviews/intakes", json=body).status_code == 409
    with shop[2]() as db:
        task = db.query(CoachTask).filter_by(order_id=first["id"]).one()
        task.status, task.delivered_text = "delivered", "Previously delivered instructor notes."
        db.commit()
    assert shop[0].get(f"/reviews/orders/{first['id']}").json()["followup_available"] is True
    with TestClient(shop[5], headers=HEADERS) as another:
        assert another.post("/reviews/intakes", json={**body, "recording_ids": [shop[4][0]]}).status_code == 404
    intake = shop[0].post("/reviews/intakes", json=body).json()
    monkeypatch.setattr(shop[3], "coaching_additional_price_cents", 1900)
    second = buy(shop, intake, "additional-session")
    assert second["id"] != first["id"] and second["amount_cents"] == 1900
    assert second["previous_order_id"] == first["id"]
    assert second["package"]["session_count"] == 1 and second["package"]["session_minutes"] == 20
    assert second["calls"] == [] and second["followup_available"] is False
    assert shop[0].get(f"/reviews/orders/{first['id']}").json()["amount_cents"] == first["amount_cents"]
