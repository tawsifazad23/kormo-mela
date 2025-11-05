from datetime import datetime, timedelta, timezone
from jose import jwt
from .config import AUTH_SECRET, ACCESS_TTL_SECONDS, REFRESH_TTL_SECONDS, ALGO, ISSUER

def _encode(payload: dict, ttl: int) -> str:
    now = datetime.now(timezone.utc)
    body = {
        "iss": ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        **payload
    }
    return jwt.encode(body, AUTH_SECRET, algorithm=ALGO)

def issue_access(user_id: int, phone: str) -> str:
    return _encode({"sub": str(user_id), "phone": phone, "scope": "access"}, ACCESS_TTL_SECONDS)

def issue_refresh(user_id: int, phone: str) -> str:
    return _encode({"sub": str(user_id), "phone": phone, "scope": "refresh"}, REFRESH_TTL_SECONDS)

def decode_token(token: str) -> dict:
    return jwt.decode(token, AUTH_SECRET, algorithms=[ALGO], issuer=ISSUER)
