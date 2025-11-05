from .db import SessionLocal
from .models import Provider

def run():
    db = SessionLocal()
    if db.query(Provider).count() == 0:
        p = Provider(
            name="Abdul Karim",
            verified=True,
            rating_avg=4.7,
            skills="driver,english",
            price_band="mid",
            lat=23.7808,
            lon=90.2792,
        )
        db.add(p)
        db.commit()
    db.close()

if __name__ == "__main__":
    run()
