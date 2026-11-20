"""Password hashing and signed session cookies for operator login (Phase 6).

Operator endpoints take sessions via the `aquarium_session` cookie instead of the
shared X-Operator-Key. Devices keep the device key (`X-Device-Key`).
"""
import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import User

SESSION_COOKIE = "aquarium_session"
SESSION_HOURS = 8


def hash_password(password: str, salt: str = "") -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", (password + salt).encode(), settings.secret_key.encode(), 100_000
    ).hex()


def verify_password(stored: str, password: str, salt: str = "") -> bool:
    return hmac.compare_digest(stored, hash_password(password, salt))


def _encode(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    data = base64.urlsafe_b64encode(json.dumps({"id": user.id, "exp": exp.isoformat()}).encode()).decode().rstrip("=")
    sig = hmac.new(settings.secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
    return f"{data}.{sig}"


def _decode(token: Optional[str]) -> Optional[User]:
    if not token or "." not in token:
        return None
    data, sig = token.rsplit(".", 1)
    expected = hmac.new(settings.secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    payload = json.loads(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)))
    if datetime.fromisoformat(payload["exp"]) < datetime.now(timezone.utc):
        return None
    with SessionLocal() as db:
        return db.get(User, payload["id"])


def require_user(session: Optional[str] = Cookie(None, alias=SESSION_COOKIE)) -> User:
    user = _decode(session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="login required")
    return user
