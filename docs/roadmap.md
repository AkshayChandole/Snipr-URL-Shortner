# Snipr — Roadmap

Implementation plan and progress tracker. **Update this file in every commit**:
tick the item you completed and refresh "Current status".

Legend: `[x]` done · `[ ]` to do

---

## Current status

- **Milestone:** 1 — Backend core (not started)
- **Last completed:** Milestone 0 — Foundation
- **Next commit:** M1 #1 — typed application settings (`pydantic-settings`)
- **Notes:** The public "create link" endpoint is deliberately deferred to
  Milestone 2, because link creation requires login. Milestone 1 builds and
  tests everything underneath it.

---

## Milestone 0 — Foundation ✅

- [x] Repository setup (`.gitignore`, `.editorconfig`, `.gitattributes`, README, license)
- [x] System design document (`docs/design.md`)
- [x] Backend scaffold: FastAPI app factory, `/healthz`, first test
- [x] Backend tooling: Ruff, mypy (strict), pytest + coverage
- [x] Frontend scaffold: Vite, React 19, TypeScript strict, Oxlint, Prettier
- [x] docker-compose for local PostgreSQL + Redis
- [x] CI: GitHub Actions (backend, frontend, secret scan)
- [x] Dependabot
- [x] pre-commit hooks (hygiene, gitleaks, Ruff, Prettier, Oxlint)
- [x] TypeScript 7 upgrade
- [x] AI agent guide (`AGENTS.md`) and this roadmap

## Milestone 1 — Backend core

Goal: a link stored in Postgres can be resolved through `GET /{code}`, served
from the Redis cache, with correct status codes and tests against real
Postgres and Redis.

- [ ] 1. Typed settings (`pydantic-settings`), validated at startup
- [ ] 2. RFC 7807 problem-details error responses and exception handlers
- [ ] 3. Async database layer (SQLAlchemy engine/session, lifespan, `Depends`)
- [ ] 4. Alembic setup (async) with constraint naming convention
- [ ] 5. Test infrastructure: testcontainers Postgres, per-test rollback
- [ ] 6. `users` and `links` models + first migration
- [ ] 7. Short code generator and custom alias rules (reserved words)
- [ ] 8. Target URL validation (schemes, length, self/shortener domains)
- [ ] 9. Link repository (DB access, unique-violation mapping)
- [ ] 10. Link service (create with collision retry, resolve by code)
- [ ] 11. Redis client (lifespan) + testcontainers Redis
- [ ] 12. Link cache (cache-aside, negative caching, invalidation)
- [ ] 13. Redirect endpoint `GET /{code}` (302 / 404 / 410, cache headers)
- [ ] 14. `/readyz` readiness probe (DB + Redis)
- [ ] 15. Backend README: local setup, migrations, tests

## Milestone 2 — Authentication

- [ ] Email/password registration and login (Argon2id)
- [ ] Access JWT + rotating refresh tokens (httpOnly cookie, reuse detection)
- [ ] GitHub OAuth login
- [ ] Turnstile CAPTCHA on registration
- [ ] `POST /api/v1/links` (authenticated link creation)

## Milestone 3 — Link management

- [ ] List (cursor pagination, search), get, update, delete links
- [ ] Custom aliases and expiry via the API
- [ ] Ownership checks (404 for other users' links)
- [ ] Rate limiting (Redis sliding window)
- [ ] Google Safe Browsing check on create/update

## Milestone 4 — Analytics

- [ ] `EventPublisher` / `EventConsumer` interfaces
- [ ] Redis Streams implementation; click events from the redirect path
- [ ] Analytics worker (batching, enrichment, idempotent writes, crash recovery)
- [ ] Daily aggregates and stats API
- [ ] `max_clicks` enforcement via Redis counter
- [ ] Raw click retention (monthly partitions, drop after 90 days)

## Milestone 5 — Frontend

- [ ] Tailwind, shadcn/ui, routing, TanStack Query, API client
- [ ] Auth flows (register, login, GitHub, token refresh)
- [ ] Dashboard: list, create, edit, delete links
- [ ] Analytics charts
- [ ] QR codes

## Milestone 6 — Extras

- [ ] API keys (create, list, revoke; hashed storage)
- [ ] `Idempotency-Key` support on `POST /links`

## Milestone 7 — Observability

- [ ] Structured JSON logging with request IDs
- [ ] Prometheus metrics
- [ ] Sentry (backend + frontend)

## Milestone 8 — Deployment

- [ ] Production Docker images (multi-stage)
- [ ] Free-tier hosting: frontend, backend, Postgres, Redis
- [ ] CD pipeline and migrations as a release step

## Milestone 9 — Polish

- [ ] Playwright end-to-end tests
- [ ] k6 load test
- [ ] README with architecture diagram and screenshots
