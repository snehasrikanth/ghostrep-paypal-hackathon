"""Separate coach privilege; an anonymous athlete cookie is never sufficient."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import session_cookie_params, settings_dep
from app.database import get_db
from app.models.commerce import CoachSession

_attempts = {}


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${digest}"


def verify_password(password: str, expected: str) -> bool:
    try:
        kind, salt, digest = expected.split("$")
        if kind != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError):
        return False


def coach_cookie(settings):
    return settings.session_cookie + "_staff"


def require_coach(request: Request, db: Session = Depends(get_db), settings=Depends(settings_dep)):
    token = request.cookies.get(coach_cookie(settings), "")
    row = db.get(CoachSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    if not row or row.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Coach sign-in required.")
    if row.demo and not settings.simulator_available:
        raise HTTPException(401, "Development coach sessions are disabled.")
    return row


def sign_in(db, response: Response, settings, *, demo=False):
    token = secrets.token_urlsafe(32)
    identity = "Sample coach" if demo else settings.coach_display_name
    db.add(CoachSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), identity=identity,
                        demo=demo, expires_at=datetime.now(timezone.utc) + timedelta(hours=8)))
    db.commit()
    params = {**session_cookie_params(settings), "max_age": 8 * 3600}
    response.set_cookie(coach_cookie(settings), token, **params)
    return {"identity": identity, "demo": demo}


def rate_limit(request):
    # Minimal local protection. Hosted builds also need a reverse-proxy login rate limit.
    address = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = [t for t in _attempts.get(address, []) if now - t < 300]
    _attempts[address] = recent + [now]
    if len(recent) >= 8:
        raise HTTPException(429, "Too many sign-in attempts. Try again in five minutes.")
