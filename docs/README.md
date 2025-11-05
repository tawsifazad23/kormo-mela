# Kormo Mela

A verified service-provider marketplace for Bangladesh & beyond.
Trust-first matching, low-latency booking, regional payments, multilingual UX.

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Architecture](#architecture)
- [Service Catalog](#service-catalog)
- [Data Model](#data-model)
- [Domain Events](#domain-events)
- [Local Development (Docker)](#local-development-docker)
- [API Quickstart](#api-quickstart)
- [Configuration](#configuration)
- [Testing](#testing)
- [Observability & Ops](#observability--ops)
- [Security & Privacy](#security--privacy)
- [Roadmap](#roadmap)
- [Repo Structure](#repo-structure)
- [Contributing & Git Workflow](#contributing--git-workflow)
- [License](#license)

---

## Executive Summary

Kormo Mela connects vetted providers (drivers, housekeepers, etc.) with households. The platform emphasizes trust, speed, and reliability: verified identities, escrow-style payments, masked chat, and a low-latency booking flow. This repository contains the backend services, gateway, and local infrastructure for running the full system end-to-end.

**SLO targets (MVP):**

- Search P95: < 300 ms cached, < 900 ms cold
- Booking confirm path P95 (incl. payment hold): ≤ 1.2 s
- Availability: ≥ 99% (MVP), blue/green deploys

---

## Architecture

### Tech Stack

- **Mobile:** React Native + FCM
- **Backend:** FastAPI (domain services), Go (booking & matchmaker)
- **Infra:** Docker/Compose → AWS ECS/EKS (Terraform)
- **Storage:** PostgreSQL + PostGIS, Redis, S3 (signed URLs)
- **Auth/Payments:** OAuth2/JWT, bKash/Nagad/Stripe adapters
- **Messaging:** Redis (MVP events/queues) → Kafka (v2)
- **Observability:** OpenTelemetry, Prometheus, Grafana, structured JSON logs

### High-Level Diagram (MVP)
```
┌──────────────┐        HTTPS         ┌───────────────┐
│  RN Mobile   │  ─────────────────▶  │   API Gateway │  NGINX
│ (Cust/Prov)  │   /auth /booking ... │ (rate-limit)  │
└──────────────┘                       └──────┬────────┘
                                              │
             ┌────────────────────────────────┼────────────────────────────────┐
             │                                │                                │
      ┌──────▼──────┐                 ┌───────▼────────┐                ┌──────▼───────┐
      │   Auth      │                 │  Booking (Go)  │                │ Notifications│
      │  FastAPI    │                 │ state machine  │                │  FastAPI     │
      └─────┬───────┘                 └──────┬─────────┘                └──────┬───────┘
            │                                 │  Redis pub/sub events            │
            │                                 └───────▶  "booking.events"  ◀─────┘
            │
      ┌─────▼────────┐                 ┌───────────────┐                 ┌──────────────┐
      │ Provider     │                 │  Search       │                 │ Payments     │
      │ FastAPI      │                 │  FastAPI      │                 │ FastAPI      │
      └──────────────┘                 └───────────────┘                 └──────────────┘

          ┌───────────────────── Core Data Plane ─────────────────────┐
          │   Postgres + PostGIS  |  Redis (cache/pubsub)  |   S3     │
          └───────────────────────────────────────────────────────────┘
```

**Today (local):**

- Gateway (NGINX)
- Auth (FastAPI)
- Booking (Go) with idempotency, audit logs, safe transitions
- Notifications (FastAPI) + Redis pub/sub
- Provider/Search/Payments service scaffolds
- Postgres + PostGIS, Redis

**Later (scale):**

- Kafka event bus, Chat (WebSockets + PII redaction), Reputation service
- CI/CD with GitHub Actions, Terraform to ECS/EKS, blue/green deploys

---

## Service Catalog

| Service       | Port | Language      | Purpose                                                    |
|---------------|------|---------------|------------------------------------------------------------|
| Gateway       | 8080 | NGINX         | Routing, rate-limits, gzip/br, request IDs                |
| Auth          | 8000 | FastAPI (Py)  | OTP login, JWT access/refresh, device binding             |
| Booking       | 8001 | Go            | Low-latency state machine, idempotency, audit             |
| Provider      | 8002 | FastAPI (Py)  | Provider profiles, skills, availability, pricing          |
| Search        | 8003 | FastAPI (Py)  | Geospatial search (PostGIS), caching                      |
| Payments      | 8004 | FastAPI (Py)  | bKash/Nagad/Stripe adapters; escrow flow                  |
| Notifications | 8005 | FastAPI (Py)  | FCM/SMS fan-out; event subscribers                        |
| Postgres      | 5432 | —             | Relational source of truth (with PostGIS)                 |
| Redis         | 6379 | —             | Cache & pub/sub backbone                                  |

---

## Data Model

Core tables (MVP implemented/scaffolded):

- **bookings** `(id, customer_id, provider_id, service_type, start_date, end_date, status, created_at, updated_at, booking_window)`
  - Overlap protection: GiST constraint on `(provider_id, booking_window)`
- **user_devices** `(user_id, push_token, platform, created_at)` for push delivery
- **audit_log** `(booking_id, actor_id, action, from_status, to_status, meta, created_at)`
- **idempotency_keys** `(key, method, path, request_hash, response_code, response_body, created_at)`

**Coming soon:** users, providers, customers, payments, messages, reviews, addresses, etc.

---

## Domain Events

**Channel:** `booking.events` (Redis pub/sub in MVP; Kafka topic in v2)

**Envelope:**
```json
{
  "type": "booking.created|booking.accepted|booking.confirmed|booking.completed|booking.canceled",
  "id": 123,
  "actor_id": 1,
  "customer_id": 1,
  "provider_id": 1,
  "status": "PENDING|ACCEPTED|CONFIRMED|COMPLETED|CANCELED",
  "title": "Booking created",
  "body": "Booking #123 created",
  "meta": {}
}
```

**Consumers (MVP):** Notifications (push fan-out)

**Future consumers:** Analytics, emails/SMS, reputation, admin feeds

---

## Local Development (Docker)

### Prereqs

- Docker & Docker Compose
- bash, curl, jq (or Postman)

### Up
```bash
docker compose up -d --build
curl -s http://localhost:8080/health    # {"status":"ok"}
```

**Health endpoints:**

- `/auth/health`, `/booking/health`, `/notifications/health` → `{"status":"ok"}`

### Down
```bash
docker compose down -v
```

---

## API Quickstart

### 1) Get access token (dev refresh shortcut)
```bash
ACCESS=$(curl -s -X POST http://localhost:8080/auth/auth/token/refresh \
  -H "Authorization: Bearer $REFRESH" | jq -r '.access_token')
```

### 2) Register device (for pushes)
```bash
curl -s -X POST http://localhost:8080/provider/devices/register \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"push_token":"sim-user-123","platform":"ios"}'
```

### 3) Create booking (idempotent)
```bash
IDEK="idemp-$(date +%s)"
BID=$(curl -s -X POST http://localhost:8080/booking/bookings \
  -H "Authorization: Bearer $ACCESS" \
  -H "Idempotency-Key: $IDEK" \
  -H "Content-Type: application/json" \
  -d '{"provider_id":1,"service_type":"driver","start_date":"2025-12-15T09:00:00Z","end_date":"2025-12-15T17:00:00Z"}' | jq -r '.id')
echo "Booking Created: $BID"
```

### 4) State transitions
```bash
curl -s -X POST http://localhost:8080/booking/bookings/$BID/accept  -H "Authorization: Bearer $ACCESS" >/dev/null
curl -s -X POST http://localhost:8080/booking/bookings/$BID/confirm -H "Authorization: Bearer $ACCESS" >/dev/null
curl -s -X POST http://localhost:8080/booking/bookings/$BID/complete -H "Authorization: Bearer $ACCESS" >/dev/null
```

### 5) Verify notifications & audit
```bash
docker compose logs --tail=200 notifications

docker compose exec -T postgres psql -U kormo -d kormo -c \
"SELECT booking_id,action,from_status,to_status,created_at FROM audit_log WHERE booking_id=$BID ORDER BY id;"
```

---

## Configuration

### Database (Compose defaults)

- `POSTGRES_DB=kormo`, `POSTGRES_USER=kormo`, `POSTGRES_PASSWORD=kormo`

### Typical service env

- `DB_HOST=postgres`, `DB_PORT=5432`, `DB_USER=kormo`, `DB_PASS=kormo`, `DB_NAME=kormo`
- `AUTH_SECRET=please-change-me-in-prod`
- `REDIS_HOST=redis`, `REDIS_PORT=6379`
- `NOTIFY_BASE=http://notifications:8005` (if direct calls used)

### Production

- Secrets in AWS Secrets Manager
- TLS at edge (ALB/CloudFront), WAF, rate limits
- S3 signed URLs for media/KYC (SSE-KMS)

---

## Testing

- **Unit:** domain logic (`go test ./...`, `pytest`)
- **Integration:** Compose smoke tests (curl/Postman collections)
- **Contract:** OpenAPI schema checks (to be generated)
- **Load:** k6 scenarios (search spikes, booking hot path, fan-out)
- **Security:** dependency scans, ZAP baseline, secrets scanning

---

## Observability & Ops

- **Health:** `/health` (liveness), `/ready` (readiness)
- **Tracing:** OpenTelemetry (propagate trace IDs via gateway)
- **Metrics:** Prometheus counters/histograms (API latency, OTP success, booking transitions, notification deliverability)
- **Logs:** Structured JSON (no PII), correlation by request/trace IDs

---

## Security & Privacy

- OAuth2/JWT (short access, refresh rotation)
- PII minimization; KYC assets via S3 signed URLs (SSE-KMS)
- Strict audit trails; append-only admin audit
- WAF & rate limiting in production
- Secrets never baked into images

---

## Roadmap

-  Compose stack, gateway, health checks
-  Booking engine (Go): state machine, idempotency, audit
-  Redis pub/sub events → Notifications fan-out
-  Chat (WebSockets) + PII redaction + moderation
-  Payments adapters (bKash/Nagad/Stripe) + escrow hold/capture/refund
-  Search tuning + PostGIS indexes + caching policy
-  OpenTelemetry/Prometheus/Grafana + CI/CD
-  Kafka event bus (v2), reputation service

---

## Repo Structure
```
.
├── docker-compose.yml
├── gateway/
│   └── nginx.conf
├── infra/
│   └── db/
│       └── init.sql
├── services/
│   ├── auth/
│   ├── booking-go/
│   │   ├── go.mod
│   │   ├── Dockerfile
│   │   └── main.go
│   ├── notifications/
│   │   ├── Dockerfile
│   │   └── main.py
│   ├── provider/
│   ├── search/
│   └── payments/
└── mobile/               # (placeholder RN app)
```

---

## Contributing & Git Workflow

### Branch Strategy

- `main` — always deployable; protected (no direct pushes)
- `feat/*` — new features (`feat/chat-ws`)
- `fix/*` — bug fixes
- `ops/*` — infra/CI
- `docs/*` — documentation only

### Conventional Commits
```
feat(booking): add redis domain events
fix(gateway): correct upstream health route
docs(readme): add architecture diagram
```

### First Push to GitHub
```bash
git init
git add .
git commit -m "feat: MVP stack (auth, booking-go, notifications, gateway, infra)"
git branch -M main
git remote add origin git@github.com:<your-username>/kormo-mela.git
git push -u origin main
```

**Protect main** (GitHub → Settings → Branches)

- Require PRs, status checks, ≥1 review
- Dismiss stale approvals on new commits
- Restrict who can push

### Release tagging
```bash
git tag v0.1.0 -m "MVP: booking engine + notifications via Redis events"
git push origin v0.1.0
```

### Add:

- `LICENSE` (Apache-2.0 suggested)
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/{bug_report.md,feature_request.md}`
- `CODEOWNERS`

---

## License

Apache-2.0. See LICENSE.