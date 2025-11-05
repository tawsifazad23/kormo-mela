from fastapi import FastAPI, Depends, HTTPException
from .routers import providers
from .models import Base
from .db import engine, SessionLocal
from pydantic import BaseModel
from sqlalchemy import text

app = FastAPI(title="Provider Service", version="0.1.0")

# Temporary auth stub until Auth service integration
def auth_required():
    return {"id": 1}

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

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

app.include_router(providers.router)

# ✅ Device registration
class DeviceRegisterReq(BaseModel):
    push_token: str
    platform: str = "ios"  # or android/web

@app.post("/devices/register")
def register_device(
    body: DeviceRegisterReq,
    db=Depends(get_db),
    user=Depends(auth_required)
):
    try:
        db.execute(
            text("""
                INSERT INTO user_devices (user_id, push_token, platform)
                VALUES (:uid, :token, :plat)
                ON CONFLICT (user_id, push_token) DO NOTHING
            """),
            {"uid": user["id"], "token": body.push_token, "plat": body.platform}
        )
        db.commit()
        return {"registered": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"DB error: {str(e)}")
