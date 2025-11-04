# Kormo Mela

A verified service provider marketplace (Bangladesh → Morocco).
MVP stack: FastAPI + Go, PostgreSQL + PostGIS, Redis, S3, Docker, NGINX gateway.

## Repo Layout
/services/{auth,provider,customer,search,booking-go,payments,notifications,chat}
mobile/  infra/  gateway/  ops/  docs/  .github/

## Local Dev (next step)
- docker compose up --build
- Gateway at http://localhost:8080
- Health checks will be at /auth/health, /booking/health, etc.

## Standards
- Conventional commits
- Each service: /health and /ready
- OpenAPI documented endpoints

## Roadmap
1) Compose baseline (auth + booking-go + postgres + redis + gateway)
2) Provider service + PostGIS
3) Auth OTP/JWT
4) Search + Redis cache
5) Booking state machine (Go) w/ idempotency
