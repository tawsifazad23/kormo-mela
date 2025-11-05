-- mkdir -p infra/db
-- cat > infra/db/init.sql <<'EOF'
-- -- Enable PostGIS in the kormo database
-- CREATE EXTENSION IF NOT EXISTS postgis;
-- CREATE EXTENSION IF NOT EXISTS postgis_topology;
-- EOF

-- -- === Phase-1 Hardening: overlap constraint + audit log ===

-- -- 1) required for btree equality in GiST
-- CREATE EXTENSION IF NOT EXISTS btree_gist;

-- -- 2) generated range column for time window
-- ALTER TABLE bookings
--   ADD COLUMN IF NOT EXISTS booking_window tstzrange
--   GENERATED ALWAYS AS (tstzrange(start_date, end_date, '[)')) STORED;

-- -- 3) exclusion constraint: prevent overlapping provider windows
-- DO $$
-- BEGIN
--   IF NOT EXISTS (
--     SELECT 1 FROM pg_constraint
--     WHERE conname = 'bookings_no_overlap'
--   ) THEN
--     ALTER TABLE bookings
--       ADD CONSTRAINT bookings_no_overlap
--       EXCLUDE USING gist (
--         provider_id WITH =,
--         booking_window WITH &&
--       )
--       WHERE (status IN ('PENDING','ACCEPTED','CONFIRMED'));
--   END IF;
-- END$$;

-- -- 4) audit log for transitions
-- CREATE TABLE IF NOT EXISTS audit_log (
--   id           BIGSERIAL PRIMARY KEY,
--   booking_id   BIGINT NOT NULL,
--   actor_id     BIGINT NOT NULL,
--   action       TEXT   NOT NULL,    -- e.g., create|accept|confirm|complete|cancel
--   from_status  TEXT,
--   to_status    TEXT,
--   meta         JSONB  DEFAULT '{}'::jsonb,
--   created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );

-- CREATE INDEX IF NOT EXISTS idx_audit_log_booking ON audit_log(booking_id);
-- infra/db/init.sql
-- Create needed extensions (safe if rerun on a fresh DB)
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ========================
-- Core tables
-- ========================

-- 1) bookings
CREATE TABLE IF NOT EXISTS bookings (
  id            BIGSERIAL PRIMARY KEY,
  customer_id   BIGINT NOT NULL,
  provider_id   BIGINT NOT NULL,
  service_type  TEXT   NOT NULL,
  start_date    TIMESTAMPTZ NOT NULL,
  end_date      TIMESTAMPTZ NOT NULL,
  location_lat  DOUBLE PRECISION,
  location_lon  DOUBLE PRECISION,
  price_band    TEXT,
  status        TEXT   NOT NULL DEFAULT 'PENDING',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  -- generated window for overlap checks
  booking_window TSTZRANGE GENERATED ALWAYS AS (tstzrange(start_date, end_date, '[]')) STORED
);

-- status helpers
CREATE INDEX IF NOT EXISTS idx_bookings_provider ON bookings(provider_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status   ON bookings(status);

-- enforce valid statuses (basic CHECK)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'bookings_status_check'
  ) THEN
    ALTER TABLE bookings
      ADD CONSTRAINT bookings_status_check
      CHECK (status IN ('PENDING','ACCEPTED','CONFIRMED','COMPLETED','CANCELED'));
  END IF;
END$$;

-- exclusion constraint to prevent overlap while active
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'bookings_no_overlap'
  ) THEN
    ALTER TABLE bookings
      ADD CONSTRAINT bookings_no_overlap
      EXCLUDE USING gist (
        provider_id WITH =,
        booking_window WITH &&
      )
      WHERE (status IN ('PENDING','ACCEPTED','CONFIRMED'));
  END IF;
END$$;

-- 2) idempotency cache
CREATE TABLE IF NOT EXISTS idempotency_keys (
  key           TEXT PRIMARY KEY,
  method        TEXT NOT NULL,
  path          TEXT NOT NULL,
  request_hash  TEXT NOT NULL,
  response_code INTEGER NOT NULL,
  response_body JSONB NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3) device registry for notifications
CREATE TABLE IF NOT EXISTS user_devices (
  user_id    BIGINT NOT NULL,
  push_token TEXT   NOT NULL,
  platform   TEXT   NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, push_token)
);

-- 4) audit log
CREATE TABLE IF NOT EXISTS audit_log (
  id           BIGSERIAL PRIMARY KEY,
  booking_id   BIGINT NOT NULL,
  actor_id     BIGINT NOT NULL,
  action       TEXT   NOT NULL,   -- create|accept|confirm|complete|cancel
  from_status  TEXT,
  to_status    TEXT,
  meta         JSONB  NOT NULL DEFAULT '{}'::jsonb,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_booking ON audit_log(booking_id);

