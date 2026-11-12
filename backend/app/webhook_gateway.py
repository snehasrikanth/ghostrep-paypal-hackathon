"""Public tunnel target: only signed PayPal webhook POSTs reach the private API."""
import httpx
from fastapi import FastAPI, HTTPException, Request, Response

PATH = "/reviews/paypal/webhook"
UPSTREAM = "http://127.0.0.1:8110" + PATH
SIGNATURE_HEADERS = ("paypal-auth-algo", "paypal-cert-url", "paypal-transmission-id",
                     "paypal-transmission-sig", "paypal-transmission-time")


def create_gateway(transport=None):
    gateway = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @gateway.post(PATH)
    async def forward(request: Request):
        if any(not request.headers.get(key) for key in SIGNATURE_HEADERS):
            raise HTTPException(400, "PayPal signature headers required.")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 1_000_000:
                raise HTTPException(413, "Webhook too large.")
        headers = {key: request.headers[key] for key in SIGNATURE_HEADERS}
        headers["content-type"] = "application/json"
        try:
            async with httpx.AsyncClient(timeout=60, transport=transport, follow_redirects=False) as client:
                result = await client.post(UPSTREAM, content=bytes(raw), headers=headers)
        except httpx.HTTPError:
            raise HTTPException(503, "Private webhook receiver unavailable; retry required.")
        return Response(content=result.content, status_code=result.status_code, media_type="application/json")

    return gateway


app = create_gateway()
