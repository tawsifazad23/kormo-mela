import json
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from redis import Redis

from .db import get_db
from .config import REDIS_HOST, REDIS_PORT, REDIS_DB, CACHE_TTL_SECONDS

app = FastAPI(title="Search Service", version="0.1.0")

# simple global redis client (sync)
r = Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)

@app.get("/health")
def health():
    try:
        r.ping()
    except Exception:
        return {"status": "degraded"}  # still OK; search can work without cache
    return {"status": "ok"}

@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        r.ping()
        return {"ready": True}
    except Exception:
        return {"ready": False}

@app.post("/search/providers")
def search_providers(payload: dict, db: Session = Depends(get_db)):
    # validate inputs (lightweight to keep dependencies small)
    try:
        lat = float(payload["lat"])
        lon = float(payload["lon"])
        radius_km = float(payload["radius_km"])
        limit = int(payload.get("limit", 20))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid input")

    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 0 < radius_km <= 50 and 1 <= limit <= 100):
        raise HTTPException(status_code=400, detail="Out of bounds")

    cache_key = f"search:{lat:.5f}:{lon:.5f}:{radius_km:.2f}:{limit}"
    try:
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        cached = None  # cache miss or redis down; continue

    # PostGIS distance using on-the-fly geography points
    # NOTE: providers.lat/lon are floats; we wrap them in ST_MakePoint
    sql = text("""
        SELECT
          p.id, p.name, p.verified, p.rating_avg, p.skills, p.price_band, p.lat, p.lon,
          ST_Distance(
            ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
          ) / 1000.0 AS distance_km
        FROM providers p
        WHERE p.lat IS NOT NULL AND p.lon IS NOT NULL
          AND ST_DWithin(
            ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326)::geography,
            ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
            :radius_meters
          )
        ORDER BY distance_km ASC
        LIMIT :limit
    """)

    rows = db.execute(sql, {
        "lat": lat,
        "lon": lon,
        "radius_meters": int(radius_km * 1000),
        "limit": limit
    }).mappings().all()

    hits = [dict(row) for row in rows]
    resp = {"count": len(hits), "hits": hits}

    try:
        r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(resp))
    except Exception:
        pass  # no cache is fine

    return resp
