"""Feedback stays useful and private before checkout; scheduling uses purchased entitlements."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.models.commerce import CoachConversation, CoachingCall, ReviewOrder
from app.models.entities import RecordedSet
from app.services.commerce.orders import now
from app.services.video.jobs import VideoJobRunner
from tests.test_commerce import shop, coach, HEADERS
from tests.test_live_coaching import live_order, request


def analyzed_fixture(shop):
    with shop[2]() as db:
        rec = db.get(RecordedSet, shop[4][0])
        rec.analysis_requested = True
        db.commit()
        # This explicitly synthetic pipeline never reads the placeholder media or calls AI.
        VideoJobRunner(shop[3].model_copy(update={"coaching_provider": "local", "segmentation_provider": "none"}))._process(db, rec.id, True, None)
        return rec.id


def ask(shop, rid, question="What happened in rep 3?", previous=None, request_id=None):
    return shop[0].post(f"/coaching/{rid}/chat", json={"request_id": request_id or str(uuid4()), "question": question,
        "previous_questions": previous or [], "approve_question": False})


def test_feedback_conversation_is_owned_saved_and_available_without_purchase(shop, monkeypatch):
    from app.services.meta.muse import MuseProvider
    monkeypatch.setattr(MuseProvider, "commerce_selection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No AI")))
    rid = analyzed_fixture(shop)
    assert shop[0].get(f"/recordings/{rid}").json()["id"] == rid
    assert shop[0].get(f"/analysis/{rid}").json()["detected_reps"] == 6
    assert shop[0].get(f"/coaching/{rid}/chat/conversation").json()["turns"] == []
    request_id = str(uuid4())
    response = ask(shop, rid, request_id=request_id)
    assert response.status_code == 200 and response.json()["source"] == "basic"
    assert not shop[1].posts
    assert shop[0].get("/reviews/orders").json() == []
    assert ask(shop, rid, request_id=request_id).json() == response.json()
    saved = shop[0].get(f"/coaching/{rid}/chat/conversation").json()
    assert len(saved["turns"]) == 1 and saved["turns"][0]["reply"] == response.json()
    # A fresh page/browser client with the same existing athlete session restores the conversation.
    with TestClient(shop[5], headers=HEADERS, cookies=shop[0].cookies) as revisit:
        assert revisit.get(f"/coaching/{rid}/chat/conversation").json() == saved
    with TestClient(shop[5], headers=HEADERS) as bob:
        assert bob.get(f"/recordings/{rid}").status_code == 404
        assert bob.get(f"/analysis/{rid}").status_code == 404
        assert bob.get(f"/coaching/{rid}/chat/conversation").status_code == 404
    assert shop[0].get("/coaching/missing/chat/conversation").status_code == 404


def test_follow_up_can_refer_to_the_previously_named_measured_rep(shop, monkeypatch):
    rid = analyzed_fixture(shop)
    assert ask(shop, rid).status_code == 200
    follow = ask(shop, rid, "Explain that rep.", ["What happened in rep 3?"])
    assert follow.status_code == 200
    assert any(e["rep_id"] == 3 for e in follow.json()["evidence"])
    import app.services.coaching.chat_requests as limiter
    from time import monotonic
    clock = [monotonic()]
    monkeypatch.setattr(limiter, "monotonic", lambda: clock[0])
    for index in range(8):
        clock[0] += 61
        assert ask(shop, rid, f"Explain this set, question {index}.").status_code == 200
    turns = shop[0].get(f"/coaching/{rid}/chat/conversation").json()["turns"]
    assert len(turns) == 6 and turns[-1]["question"].endswith("7.")


def test_selected_recording_states_remain_visible_and_owned(shop):
    with shop[2]() as db:
        db.get(RecordedSet, shop[4][0]).processing_status = "ESTIMATING_POSE"
        db.get(RecordedSet, shop[4][1]).normalized_path = None
        db.commit()
    rows = {r["id"]: r for r in shop[0].get("/reviews/recordings").json()}
    assert rows[shop[4][0]]["processing_status"] == "ESTIMATING_POSE"
    assert rows[shop[4][1]]["has_video"] is False
    assert shop[0].get(f"/recordings/{shop[4][0]}").status_code == 200
    assert shop[0].get(f"/media/{shop[4][1]}").status_code == 404


def test_prices_entitlements_and_sharing_scope_are_server_owned(shop):
    for pid, amount, count, minutes in [("day-coaching", 1500, 1, 20), ("month-coaching", 7900, 4, 30)]:
        order = live_order(shop, pid)
        assert (order["amount_cents"], order["package"]["session_count"], order["package"]["session_minutes"]) == (amount, count, minutes)
        assert shop[1].orders[order["provider_order_id"]]["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": f"{amount / 100:.2f}"}
        assert order["sharing"]["recording_ids"] == [shop[4][0]]
        assert order["calls"] == []
        scheduled = request(shop, order)
        assert len(scheduled["calls"]) == count
        assert all(c["meeting_url"] is None for c in scheduled["calls"])


def test_monthly_requests_preserve_local_wall_time_across_dst(shop):
    import app.services.commerce.scheduling as scheduling
    from unittest.mock import patch
    order = live_order(shop)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2027, 3, 1, 12, tzinfo=timezone.utc).astimezone(tz) if tz else datetime(2027, 3, 1, 12)
    first = datetime(2027, 3, 7, 10, tzinfo=ZoneInfo("America/New_York"))
    with patch.object(scheduling, "datetime", FixedDateTime):
        response = shop[0].post(f"/reviews/orders/{order['id']}/calls", json={"starts_at": first.isoformat(), "timezone": "America/New_York"})
    assert response.status_code == 200, response.text
    calls = response.json()["calls"]
    assert all(datetime.fromisoformat(c["requested_at"]).astimezone(ZoneInfo("America/New_York")).hour == 10 for c in calls)
    assert calls[0]["requested_at"][11:16] == "15:00"
    assert calls[1]["requested_at"][11:16] == "14:00"
    assert all(c["requested_timezone"] == "America/New_York" for c in calls)


def test_confirmed_call_change_keeps_original_until_coach_confirms(shop):
    order = request(shop, live_order(shop))
    call = order["calls"][0]
    coach(shop)
    confirm_path = f"/coach/tasks/{order['task']['id']}/calls/{call['id']}/confirm"
    original = {"starts_at": call["requested_at"], "meeting_url": "https://meet.google.com/abc-defg-hij"}
    assert shop[0].post(confirm_path, json=original).status_code == 200
    changed = (datetime.fromisoformat(call["requested_at"]) + timedelta(days=1)).isoformat()
    response = shop[0].post(f"/reviews/orders/{order['id']}/calls/{call['id']}/request", json={"starts_at": changed, "timezone": "America/New_York"})
    assert response.status_code == 200
    updated = response.json()["calls"][0]
    assert updated["status"] == "confirmed" and updated["starts_at"] == call["requested_at"]
    assert updated["meeting_url"] == original["meeting_url"] and updated["change_requested_at"] == changed
    done = shop[0].post(confirm_path, json={**original, "starts_at": changed}).json()["calls"][0]
    assert done["starts_at"] == changed and done["change_requested_at"] is None
    assert done["requested_timezone"] == "America/New_York"
    assert len(response.json()["calls"]) == 4


def test_call_cancellation_keeps_entitlement_and_refund_revokes_join_link(shop):
    order = request(shop, live_order(shop, "day-coaching")); coach(shop)
    call = order["calls"][0]
    confirm_path = f"/coach/tasks/{order['task']['id']}/calls/{call['id']}/confirm"
    body = {"starts_at": call["requested_at"], "meeting_url": "https://meet.google.com/abc-defg-hij"}
    assert shop[0].post(confirm_path, json=body).status_code == 200
    cancel = f"/reviews/orders/{order['id']}/calls/{call['id']}/cancel"
    for _ in range(2):
        canceled = shop[0].post(cancel, json={})
        assert canceled.status_code == 200 and canceled.json()["calls"][0]["meeting_url"] is None
    assert shop[0].post(confirm_path, json=body).status_code == 409
    again = shop[0].post(cancel.replace("/cancel", "/request"), json={"starts_at": call["requested_at"]})
    assert len(again.json()["calls"]) == 1
    assert shop[0].post(confirm_path, json=body).status_code == 200
    refunded = shop[0].post(f"/coach/tasks/{order['task']['id']}/refund", json={})
    assert refunded.status_code == 200 and refunded.json()["payment_state"] == "refunded"
    assert refunded.json()["calls"][0]["meeting_url"] is None
    assert shop[0].post(cancel.replace("/cancel", "/request"), json={"starts_at": call["requested_at"]}).status_code == 409
    with shop[2]() as db:
        assert db.get(CoachingCall, call["id"]).status == "canceled"
        assert db.get(ReviewOrder, order["id"]).package_json


def test_overlap_across_orders_and_pending_refund_reserves_original_time(shop):
    first = request(shop, live_order(shop, "day-coaching")); coach(shop)
    c1 = first["calls"][0]
    body = {"starts_at": c1["requested_at"], "meeting_url": "https://meet.google.com/abc-defg-hij"}
    path1 = f"/coach/tasks/{first['task']['id']}/calls/{c1['id']}/confirm"
    assert shop[0].post(path1, json=body).status_code == 200
    second = request(shop, live_order(shop, "day-coaching"))
    c2 = second["calls"][0]
    path2 = f"/coach/tasks/{second['task']['id']}/calls/{c2['id']}/confirm"
    assert shop[0].post(path2, json=body).status_code == 409
    with shop[2]() as db:
        db.get(ReviewOrder, first["id"]).payment_state = "refund_pending"; db.commit()
    assert shop[0].post(path2, json=body).status_code == 409
    with shop[2]() as db:
        db.get(ReviewOrder, first["id"]).payment_state = "refunded"; db.commit()
    assert shop[0].post(path2, json=body).status_code == 200


def test_cross_user_cannot_read_or_change_private_calls(shop):
    order = request(shop, live_order(shop)); coach(shop)
    call = order["calls"][0]
    body = {"starts_at": call["requested_at"], "meeting_url": "https://meet.google.com/abc-defg-hij"}
    assert shop[0].post(f"/coach/tasks/{order['task']['id']}/calls/{call['id']}/confirm", json=body).status_code == 200
    with TestClient(shop[5], headers=HEADERS) as bob:
        assert bob.get(f"/reviews/orders/{order['id']}").status_code == 404
        assert bob.post(f"/reviews/orders/{order['id']}/calls/{call['id']}/request", json={"starts_at": call["requested_at"]}).status_code == 404
        assert bob.post(f"/reviews/orders/{order['id']}/calls/{call['id']}/cancel", json={}).status_code == 404
        assert bob.get(f"/coach/tasks/{order['task']['id']}").status_code == 401
    wrong = shop[0].post(f"/reviews/orders/{order['id']}/calls/not-my-call/request", json={"starts_at": call["requested_at"]})
    assert wrong.status_code == 404
    bad_zone = shop[0].post(f"/reviews/orders/{order['id']}/calls/{call['id']}/request", json={"starts_at": call["requested_at"], "timezone": "Made/Up"})
    assert bad_zone.status_code == 422


def test_coach_login_still_limits_repeated_attempts(shop):
    for _ in range(8):
        assert shop[0].post("/coach/login", json={"password": "wrong"}).status_code == 401
    assert shop[0].post("/coach/login", json={"password": "wrong"}).status_code == 429


def test_primary_clip_order_survives_checkout_and_receipt(shop):
    # Exercise IDs whose UUID ordering must not choose the primary clip for us.
    live_order(shop, "day-coaching", capture=False)
    ordered = list(reversed(shop[4]))
    response = shop[0].post("/reviews/intakes", json={"question": "Compare these selected sets with clip one first.", "recording_ids": ordered, "share_with_coach": True})
    iid = response.json()["id"]
    response = shop[0].post("/reviews/orders", json={"intake_id": iid, "package_id": "month-coaching", "checkout_key": iid})
    assert response.status_code == 200
    assert response.json()["sharing"]["recording_ids"] == ordered
    assert shop[0].get(f"/reviews/orders/{response.json()['id']}").json()["sharing"]["recording_ids"] == ordered
