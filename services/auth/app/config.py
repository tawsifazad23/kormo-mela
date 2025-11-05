import os

# DB (same Postgres as other services)
DB_USER = os.getenv("DB_USER", "kormo")
DB_PASS = os.getenv("DB_PASS", "kormo")
DB_NAME = os.getenv("DB_NAME", "kormo")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# JWT
AUTH_SECRET = os.getenv("AUTH_SECRET", "dev-secret-change-me")
ACCESS_TTL_SECONDS = int(os.getenv("ACCESS_TTL_SECONDS", "900"))      # 15m
REFRESH_TTL_SECONDS = int(os.getenv("REFRESH_TTL_SECONDS", "1209600")) # 14d

ISSUER = "kormo-mela-auth"
ALGO = "HS256"
