from fastapi import FastAPI, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional
from .db import get_db, engine
from .models import Base, User
from .schemas import OTPRequest, OTPVerify, TokenPair, UserOut
from .jwt_utils import issue_access, issue_refresh, decode_token

app = FastAPI(title="Auth Service", version="0.2.0")

# Create tables if not exist (MVP; later switch to Alembic)
Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    try:
        with engine.connect() as _:
            return {"ready": True}
    except Exception:
        return {"ready": False}

# --- OTP (mock) ---
# We will accept ANY phone; the "code" is 123456 for MVP.
@app.post("/auth/otp/request")
def request_otp(payload: OTPRequest):
    # In real impl: generate + send via SMS; here we log only
    # You can view container logs to see incoming requests
    return {"ok": True, "message": "Mock OTP sent (use code 123456)"}

@app.post("/auth/otp/verify", response_model=TokenPair)
def verify_otp(payload: OTPVerify, db: Session = Depends(get_db)):
    if payload.code != "123456":
        raise HTTPException(status_code=400, detail="Invalid code")

    user = db.query(User).filter(User.phone_e164 == payload.phone).first()
    if not user:
        user = User(phone_e164=payload.phone)
        db.add(user)
        db.commit()
        db.refresh(user)

    access = issue_access(user.id, user.phone_e164)
    refresh = issue_refresh(user.id, user.phone_e164)
    return TokenPair(access_token=access, refresh_token=refresh)

# --- Protected whoami ---
@app.get("/auth/me", response_model=UserOut)
def whoami(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        claims = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if claims.get("scope") != "access":
        raise HTTPException(status_code=401, detail="Access token required")
    return UserOut(id=int(claims["sub"]), phone=claims["phone"])

# --- Refresh token endpoint ---
@app.post("/auth/token/refresh", response_model=TokenPair)
def refresh_token(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        claims = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    if claims.get("scope") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token required")

    user_id = int(claims["sub"])
    phone = claims["phone"]
    # optional: ensure user still exists
    access = issue_access(user_id, phone)
    refresh = issue_refresh(user_id, phone)
    return TokenPair(access_token=access, refresh_token=refresh)
