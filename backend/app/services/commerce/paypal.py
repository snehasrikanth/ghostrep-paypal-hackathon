"""Direct, single-merchant PayPal Sandbox REST integration. No live URL setting."""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx

SANDBOX_API = "https://api-m.sandbox.paypal.com"


class ProviderError(RuntimeError):
    pass


def cents(value) -> int:
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount * 100 != (amount * 100).to_integral_value():
            raise ValueError()
        return int(amount * 100)
    except (ValueError, InvalidOperation, TypeError, OverflowError) as exc:
        raise ProviderError("Invalid provider amount; reconciliation required.") from exc


def money(value: int) -> str:
    return f"{value // 100}.{value % 100:02d}"


class PayPal:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    def _client(self):
        return httpx.Client(base_url=SANDBOX_API, timeout=20, transport=self.transport, follow_redirects=False)

    def _access_token(self, client, *, client_token=False):
        data = {"grant_type": "client_credentials"}
        if client_token:
            data.update({"response_type": "client_token", "intent": "sdk_init"})
        auth = client.post("/v1/oauth2/token", data=data,
                           auth=(self.settings.paypal_client_id, self.settings.paypal_client_secret))
        if auth.status_code != 200:
            raise ProviderError("PayPal Sandbox authentication failed. Check backend configuration.")
        payload = auth.json()
        token = payload.get("access_token") or payload.get("client_token")
        if not isinstance(token, str) or not token:
            raise ProviderError("PayPal Sandbox authentication failed. Check backend configuration.")
        return token

    def browser_client_token(self):
        """Browser-safe SDK bootstrap token. Never expose the client secret to the frontend."""
        if not self.settings.sandbox_configured:
            raise ProviderError("PayPal Sandbox merchant credentials are not configured.")
        try:
            with self._client() as client:
                return self._access_token(client, client_token=True)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError("PayPal client token was unavailable. Reconcile before retrying.") from exc

    def request(self, method, path, body=None, key=None):
        if not self.settings.sandbox_configured:
            raise ProviderError("PayPal Sandbox merchant credentials are not configured.")
        try:
            with self._client() as client:
                token = self._access_token(client)
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                           "Prefer": "return=representation"}
                if key:
                    headers["PayPal-Request-Id"] = key
                response = client.request(method, path, json=body, headers=headers)
                if response.status_code not in {200, 201, 202, 204}:
                    # Do not expose raw provider bodies, tokens or payer details.
                    raise ProviderError("PayPal did not confirm this operation. Reconcile before retrying.")
                return response.json() if response.content else {}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError("PayPal response was uncertain. Reconcile before retrying.") from exc

    def create(self, order):
        import json
        package = json.loads(order.package_json)
        origin = self.settings.frontend_origin.rstrip("/")
        body = {"intent": "CAPTURE", "purchase_units": [{"reference_id": order.id,
                "custom_id": order.id, "invoice_id": order.id,
                "description": package["name"], "payee": {"merchant_id": order.merchant_id},
                "amount": {"currency_code": order.currency, "value": money(order.amount_cents)}}],
                "payment_source": {"paypal": {"experience_context": {
                    "brand_name": "GhostRep Coach", "shipping_preference": "NO_SHIPPING",
                    "user_action": "PAY_NOW", "return_url": f"{origin}/reviews/{order.id}?paypal=approved",
                    "cancel_url": f"{origin}/reviews/{order.id}?paypal=canceled"}}}}
        return self.request("POST", "/v2/checkout/orders", body, order.create_key)

    def retrieve(self, order_id):
        return self.request("GET", f"/v2/checkout/orders/{order_id}")

    def capture(self, order):
        return self.request("POST", f"/v2/checkout/orders/{order.provider_order_id}/capture", {}, order.capture_key)

    def capture_details(self, capture_id):
        return self.request("GET", f"/v2/payments/captures/{capture_id}")

    def refund(self, order, refund):
        return self.request("POST", f"/v2/payments/captures/{order.capture_id}/refund",
                            {"amount": {"currency_code": order.currency, "value": money(refund.amount_cents)}}, refund.request_key)

    def refund_details(self, refund_id):
        return self.request("GET", f"/v2/payments/refunds/{refund_id}")

    def verify_webhook(self, headers, event):
        if not self.settings.paypal_webhook_id:
            raise ProviderError("Webhook verification is not configured.")
        fields = {"auth_algo": "paypal-auth-algo", "cert_url": "paypal-cert-url",
                  "transmission_id": "paypal-transmission-id", "transmission_sig": "paypal-transmission-sig",
                  "transmission_time": "paypal-transmission-time"}
        if any(not headers.get(h) for h in fields.values()):
            return False
        payload = {k: headers[h] for k, h in fields.items()}
        payload.update(webhook_id=self.settings.paypal_webhook_id, webhook_event=event)
        # PayPal verifies the signature; we never download an untrusted cert URL.
        return self.request("POST", "/v1/notifications/verify-webhook-signature", payload).get("verification_status") == "SUCCESS"


def approval_link(payload):
    for link in payload.get("links", []):
        if link.get("rel") in {"payer-action", "approve"}:
            url = urlparse(link.get("href", ""))
            if url.scheme == "https" and url.hostname in {"www.sandbox.paypal.com", "sandbox.paypal.com"}:
                return link["href"]
    return None
