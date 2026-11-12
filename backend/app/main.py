from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analysis, coach_chat, coaching, demo, health, meta, profiles, program, sessions, videos, workouts
from app.api.routes import reviews, coach_workspace, paypal_webhooks, payments
from app.config import get_settings
from app.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="GhostRep API",
        version="0.1.0",
        description="Local-first movement analysis. Meta Model API is gated and off by default.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.middleware("http")
    async def protect_browser_mutations(request: Request, call_next):
        path = request.url.path
        webhook = path == "/reviews/paypal/webhook"
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not webhook:
            origin = request.headers.get("origin")
            if (origin is not None and origin != settings.frontend_origin.rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Untrusted request origin."}, status_code=403)
            if path.startswith(("/reviews/", "/coach/", "/api/payments/")) and request.headers.get("x-ghostrep-csrf") != "1":
                return JSONResponse({"detail": "Missing CSRF request header."}, status_code=403)
        response = await call_next(request)
        if path.startswith(("/reviews", "/coach", "/media", "/analysis", "/recordings", "/api/payments")):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(reviews.router)
    app.include_router(payments.router)
    app.include_router(coach_workspace.router)
    app.include_router(paypal_webhooks.router)
    app.include_router(health.router)
    app.include_router(demo.router)
    app.include_router(meta.router)
    app.include_router(profiles.router)
    app.include_router(workouts.router)
    app.include_router(program.router)
    app.include_router(sessions.router)
    app.include_router(videos.router)
    app.include_router(analysis.router)
    app.include_router(coaching.router)
    app.include_router(coach_chat.router)
    return app


app = create_app()
