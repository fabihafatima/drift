"""Demo auth: HMAC-signed user tokens; every query is scoped by the user's org."""

import hashlib
import hmac

from fastapi import Header, HTTPException, Query

from .config import settings
from .db import one


def sign(user_id: str) -> str:
    mac = hmac.new(settings.secret.encode(), user_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{user_id}.{mac}"


def _verify(token: str | None) -> dict:
    if not token or "." not in token:
        raise HTTPException(401, "Not signed in")
    user_id, _ = token.rsplit(".", 1)
    if not hmac.compare_digest(sign(user_id), token):
        raise HTTPException(401, "Invalid token")
    user = one("""SELECT u.*, o.name AS org_name, o.slug AS org_slug FROM users u JOIN orgs o ON o.id = u.org_id
                  WHERE u.id = ?""", user_id)
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


async def current_user(authorization: str | None = Header(None), token: str | None = Query(None)) -> dict:
    # async so it runs on the event loop: the SQLite connection is shared and not thread-safe.
    bearer = authorization.removeprefix("Bearer ").strip() if authorization else None
    return _verify(bearer or token)


def require_admin(user: dict) -> None:
    if user["role"] not in ("OWNER", "ADMIN"):
        raise HTTPException(403, "Admins only")
