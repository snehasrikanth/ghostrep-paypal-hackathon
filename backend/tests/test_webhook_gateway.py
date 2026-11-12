import httpx
from fastapi.testclient import TestClient
from app.webhook_gateway import create_gateway, PATH, SIGNATURE_HEADERS, UPSTREAM


def test_gateway_exposes_only_the_signed_webhook_and_strips_private_headers():
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(400, json={"detail": "Invalid signature"})
    with TestClient(create_gateway(httpx.MockTransport(receive))) as client:
        for path in ("/", "/docs", "/openapi.json", "/coach", "/profiles/me", "/api/payments/config"):
            assert client.get(path).status_code == 404
            assert client.post(path, json={}).status_code == 404
        assert client.post(PATH, json={}).status_code == 400
        headers = {key: "test" for key in SIGNATURE_HEADERS}
        headers.update(Cookie="athlete=private", Authorization="Bearer private", Origin="https://untrusted.example")
        response = client.post(PATH, json={"id": "test"}, headers=headers)
        assert response.status_code == 400
    assert len(seen) == 1 and str(seen[0].url) == UPSTREAM
    assert "cookie" not in seen[0].headers and "authorization" not in seen[0].headers and "origin" not in seen[0].headers


def test_gateway_bounds_payload_size_before_forwarding():
    def receive(request):
        raise AssertionError("Oversized body must not reach the API")
    with TestClient(create_gateway(httpx.MockTransport(receive))) as client:
        assert client.post(PATH, content=b"x" * 1_000_001, headers={key: "test" for key in SIGNATURE_HEADERS}).status_code == 413
