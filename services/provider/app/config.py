import os

DB_USER = os.getenv("DB_USER", "kormo")
DB_PASS = os.getenv("DB_PASS", "kormo")
DB_NAME = os.getenv("DB_NAME", "kormo")
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
