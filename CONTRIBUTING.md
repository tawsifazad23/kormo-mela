# Contributing

## Branching
- main: protected
- dev: default working branch
- feature: feat/<area>-<desc> (e.g., feat/auth-otp)

## Commits (Conventional)
- feat:, fix:, chore:, docs:, refactor:, test:, perf:
- Example: feat(auth): add OTP verify endpoint

## PR Rules
- Small PRs, passing tests, include manual steps + expected outputs

## Code Style
- Python: black + ruff
- Go: go fmt + staticcheck
- Every service exposes /health and /ready
- OpenAPI documented endpoints

## Secrets
- Never commit .env; provide .env.example
