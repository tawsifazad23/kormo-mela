from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os, psycopg2, json, threading, time
import redis

app = FastAPI(title="Notification Service", version="0.2.0")

DB_DSN = f"dbname={os.getenv('DB_NAME','kormo')} user={os.getenv('DB_USER','kormo')} password={os.getenv('DB_PASS','kormo')} host={os.getenv('DB_HOST','postgres')} port={os.getenv('DB_PORT','5432')}"
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
EVENT_CHANNEL = "booking.events"

def conn():
    return psycopg2.connect(DB_DSN)

# --- API health ---
@app.get("/health")
def health():
    return {"status": "ok"}

# --- Direct notify endpoint (kept) ---
class NotifyEvent(BaseModel):
    user_id: int
    title: str
    body: str
    data: dict = {}

@app.post("/notify")
def notify(evt: NotifyEvent):
    try:
        with conn() as c:
            with c.cursor() as cur:
                cur.execute("""
                    SELECT push_token, platform
                    FROM user_devices WHERE user_id=%s
                """, (evt.user_id,))
                devices = cur.fetchall()

        if not devices:
            return {"delivered": False, "reason": "no registered devices"}

        for token, platform in devices:
            print(f"[PUSH] → {platform} | {token} => {evt.title}: {evt.body}")

        return {
            "delivered": True,
            "devices": len(devices),
            "user_id": evt.user_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Background subscriber for booking events ---
def handle_event(payload: dict):
    """
    Payload schema from booking-go:
    {
      "type": "booking.created|accepted|confirmed|completed|canceled",
      "id": <booking_id>,
      "actor_id": <user_id>,
      "customer_id": <id>,
      "provider_id": <id>,
      "status": "PENDING|ACCEPTED|...|CANCELED",
      "title": "string",
      "body": "string",
      "meta": { ... }
    }
    We push to BOTH parties (customer & provider).
    """
    try:
        booking_id = payload.get("id")
        title = payload.get("title", "Booking update")
        body  = payload.get("body",  f"Booking #{booking_id} updated")
        customer_id = payload.get("customer_id")
        provider_id = payload.get("provider_id")

        targets = [u for u in [customer_id, provider_id] if u]
        if not targets:
            return

        with conn() as c:
            with c.cursor() as cur:
                # fetch all device tokens for each target
                cur.execute("""
                  SELECT user_id, push_token, platform
                  FROM user_devices
                  WHERE user_id = ANY(%s)
                """, (targets,))
                rows = cur.fetchall()

        if not rows:
            print(f"[EVENT→PUSH] booking#{booking_id} no devices registered")
            return

        for uid, token, platform in rows:
            print(f"[EVENT→PUSH] #{booking_id} → uid={uid} [{platform}|{token}] :: {title}: {body}")

    except Exception as e:
        print(f"[EVENT ERROR] {e}")

def subscriber_thread():
    # reconnect loop with simple backoff
    backoff = 1
    while True:
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            pubsub = r.pubsub()
            pubsub.subscribe(EVENT_CHANNEL)
            print(f"[SUB] listening on redis channel: {EVENT_CHANNEL}")
            for msg in pubsub.listen():
                if msg and msg.get("type") == "message":
                    data = msg.get("data")
                    try:
                        payload = json.loads(data)
                        handle_event(payload)
                    except Exception as e:
                        print(f"[SUB ERROR] bad payload: {e} :: {data}")
            backoff = 1
        except Exception as e:
            print(f"[SUB ERROR] {e}; retrying in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff*2, 30)

# Start subscriber when app starts
def start_background():
    t = threading.Thread(target=subscriber_thread, daemon=True)
    t.start()

start_background()
