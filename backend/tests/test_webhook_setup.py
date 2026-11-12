import os
import pytest
from app.webhook_setup import configure
from app.api.routes.paypal_webhooks import EVENTS


class Provider:
    def __init__(self):
        self.webhooks = []
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("webhooks-event-types"):
            return {"event_types": [{"name": name} for name in EVENTS]}
        if method == "GET":
            return {"webhooks": self.webhooks}
        result = {"id": "WH123", **body}
        self.webhooks.append(result)
        return result


def test_registration_reuses_endpoint_and_preserves_private_settings(tmp_path):
    target = tmp_path / ".env"
    target.write_text("UNRELATED=keep\nPAYPAL_WEBHOOK_ID=''\n")
    provider = Provider()
    url = "https://example.com/reviews/paypal/webhook"
    result = configure(url, provider, target)
    assert result["webhook_id"] == "WH123" and not result["reused"]
    assert "UNRELATED=keep" in target.read_text()
    assert "PAYPAL_WEBHOOK_ID='WH123'" in target.read_text()
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert configure(url, provider, target)["reused"]
    assert len([call for call in provider.calls if call[0] == "POST"]) == 1


@pytest.mark.parametrize("url", ["http://example.com/reviews/paypal/webhook", "https://localhost/reviews/paypal/webhook",
                                 "https://example.com/coach", "https://example.com/reviews/paypal/webhook?key=secret"])
def test_registration_rejects_invalid_callback_before_network(tmp_path, url):
    provider = Provider()
    with pytest.raises(ValueError):
        configure(url, provider, tmp_path / ".env")
    assert not provider.calls
