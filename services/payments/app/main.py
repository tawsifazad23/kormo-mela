from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
import os, psycopg2, json

app = FastAPI(title="payments")

DB_DSN = f"dbname={os.getenv('DB_NAME','kormo')} user={os.getenv('DB_USER','kormo')} password={os.getenv('DB_PASS','kormo')} host={os.getenv('DB_HOST','postgres')} port={os.getenv('DB_PORT','5432')}"
WEBHOOK_SECRET = os.getenv("PAYMENTS_WEBHOOK_SECRET", "dev-secret")

def conn():
    return psycopg2.connect(DB_DSN)

@app.get("/health")
def health():
    return {"status": "ok"}

class PaymentIntentReq(BaseModel):
    booking_id: int
    amount_minor: int  # e.g., 80000 = 800.00
    currency: str = "BDT"

@app.post("/payments/intent")
def create_intent(body: PaymentIntentReq):
    # In real life, call Stripe/Adyen/etc. Here we return a fake client_secret
    return {
        "client_secret": f"pi_test_{body.booking_id}",
        "booking_id": body.booking_id,
        "amount_minor": body.amount_minor,
        "currency": body.currency
    }

class WebhookEvent(BaseModel):
    type: str    # e.g., "payment.succeeded"
    data: dict   # should include booking_id

@app.post("/payments/webhook")
def webhook(evt: WebhookEvent, x_signature: str = Header(None)):
    if x_signature != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid signature")

    if evt.type != "payment.succeeded":
        # Accept other events as no-ops for now
        return {"received": True, "ignored": True}

    booking_id = evt.data.get("booking_id")
    if not booking_id:
        raise HTTPException(status_code=400, detail="missing booking_id")

    with conn() as c:
        with c.cursor() as cur:
            # Lock the row to make the transitions atomic & idempotent
            cur.execute("SELECT status FROM bookings WHERE id=%s FOR UPDATE", (booking_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="booking not found")

            status = row[0]

            # No-op states
            if status in ("COMPLETED", "CANCELED"):
                return {"received": True, "booking_id": booking_id, "final_status": status}

            # Advance through the happy path up to COMPLETED
            if status == "PENDING":
                cur.execute("UPDATE bookings SET status='ACCEPTED', updated_at=NOW() WHERE id=%s", (booking_id,))
                status = "ACCEPTED"

            if status == "ACCEPTED":
                cur.execute("UPDATE bookings SET status='CONFIRMED', updated_at=NOW() WHERE id=%s", (booking_id,))
                status = "CONFIRMED"

            if status == "CONFIRMED":
                cur.execute("UPDATE bookings SET status='COMPLETED', updated_at=NOW() WHERE id=%s", (booking_id,))
                status = "COMPLETED"

    return {"received": True, "booking_id": booking_id, "final_status": status}
