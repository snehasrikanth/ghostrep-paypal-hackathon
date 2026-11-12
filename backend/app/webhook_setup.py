"""Register this copy's HTTPS callback on its existing Sandbox REST app."""
import argparse
import os
from pathlib import Path
from urllib.parse import urlparse

from app.api.routes.paypal_webhooks import EVENTS
from app.config import Settings
from app.services.commerce.paypal import PayPal


def configure(url, provider, target):
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.hostname in {"localhost", "127.0.0.1"}
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path != "/reviews/paypal/webhook"):
        raise ValueError("Use a public HTTPS URL ending /reviews/paypal/webhook, without query parameters.")
    available = {item["name"] for item in provider.request("GET", "/v1/notifications/webhooks-event-types").get("event_types", [])}
    wanted = EVENTS & available
    required = {"PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.PENDING", "PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED"}
    if not required <= wanted:
        raise ValueError("The provider did not advertise the required capture events. No changes made.")
    existing = next((w for w in provider.request("GET", "/v1/notifications/webhooks").get("webhooks", []) if w.get("url") == url), None)
    events = [{"name": name} for name in sorted(wanted)]
    if existing:
        webhook = existing
        if {e["name"] for e in webhook.get("event_types", [])} != wanted:
            provider.request("PATCH", f"/v1/notifications/webhooks/{webhook['id']}",
                             [{"op": "replace", "path": "/event_types", "value": events}])
    else:
        webhook = provider.request("POST", "/v1/notifications/webhooks", {"url": url, "event_types": events})
    identifier = webhook.get("id", "")
    if not isinstance(identifier, str) or not identifier.isalnum():
        raise ValueError("Provider returned an invalid webhook ID. Local configuration was not changed.")
    lines = target.read_text().splitlines() if target.exists() else []
    lines = [line for line in lines if line.split("=", 1)[0].strip() != "PAYPAL_WEBHOOK_ID"]
    lines.append(f"PAYPAL_WEBHOOK_ID='{identifier}'")
    temporary = target.with_name(".env.webhook-setup.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return {"webhook_id": identifier, "url": url, "events": sorted(wanted), "reused": bool(existing)}


def main():
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    print(json.dumps(configure(args.url, PayPal(Settings()), Path(__file__).resolve().parents[2] / ".env"), indent=2))


if __name__ == "__main__":
    main()
