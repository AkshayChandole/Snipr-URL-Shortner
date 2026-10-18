# Snipr — System Design

> Snipr is a production-grade URL shortener with user accounts, custom aliases,
> link expiry, click analytics, QR codes and API keys.
>
> This document explains **what** we are building, **which options** we
> considered for each major decision, and **why** we chose the one we did.
> It is a living document: when a decision changes, update the relevant section
> and record the change in the [Changelog](#18-changelog).

---

## Table of contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Requirements](#2-requirements)
3. [Capacity estimation](#3-capacity-estimation)
4. [High-level architecture](#4-high-level-architecture)
5. [Short code generation](#5-short-code-generation)
6. [Redirect strategy](#6-redirect-strategy)
7. [Data storage and data model](#7-data-storage-and-data-model)
8. [Caching](#8-caching)
9. [Analytics pipeline](#9-analytics-pipeline)
10. [Authentication and authorization](#10-authentication-and-authorization)
11. [Security and abuse prevention](#11-security-and-abuse-prevention)
12. [API design](#12-api-design)
13. [Technology choices](#13-technology-choices)
14. [Observability, testing and delivery](#14-observability-testing-and-delivery)
15. [Deployment (free tier)](#15-deployment-free-tier)
16. [Scaling beyond the free tier](#16-scaling-beyond-the-free-tier)
17. [Open questions and future work](#17-open-questions-and-future-work)
18. [Changelog](#18-changelog)

---

## 1. Goals and non-goals

### Goals
- Turn a long URL into a short, non-guessable link and redirect quickly and reliably.
- Give authenticated users a dashboard to manage links and see analytics.
- Be **production grade**: secure by default, observable, tested, reproducible
  builds and automated delivery.
- Have an architecture that can scale to 100M+ links **without a rewrite**, even
  though the first deployment runs on free-tier infrastructure.

### Non-goals (for now)
- Password-protected links.
- Teams / organisations and role-based sharing.
- Multiple custom domains per user (e.g. `go.mycompany.com`).
- Real-time (sub-second) analytics. A few seconds of delay is acceptable.

---

## 2. Requirements

### 2.1 Functional

| #   | Requirement                                                            | Milestone |
|-----|------------------------------------------------------------------------|-----------|
| F1  | Register / log in with email + password or GitHub OAuth                | MVP       |
| F2  | Authenticated users create short links (**login required**)            | MVP       |
| F3  | `GET /{code}` redirects to the target URL                              | MVP       |
| F4  | Optional custom alias (e.g. `/my-portfolio`)                           | MVP       |
| F5  | Optional expiry by date and/or by maximum click count                  | MVP       |
| F6  | Dashboard: list, search, edit target, deactivate, delete links         | MVP       |
| F7  | Per-link analytics: clicks over time, referrers, countries, devices    | v1        |
| F8  | QR code (PNG / SVG) for each link                                      | v1        |
| F9  | API keys for programmatic access                                       | v1        |

### 2.2 Non-functional

| Attribute        | Target                                                                         |
|------------------|--------------------------------------------------------------------------------|
| Redirect latency | p99 < 50 ms server-side on a cache hit                                         |
| Availability     | Redirect path is the priority; the dashboard may degrade before redirects do   |
| Read/write ratio | ~100 : 1 (redirects : creations)                                               |
| Non-guessability | Short codes must not be enumerable                                             |
| Analytics        | Eventually consistent (seconds); must **never** slow down a redirect           |
| Privacy          | No raw IP addresses stored; salted hash + derived country only                 |
| Security         | OWASP Top 10 mitigated; abuse controls on every write path                     |
| Data retention   | Raw click events: **90 days**. Daily aggregates: **kept forever**              |

---

## 3. Capacity estimation

These numbers describe the **design target**, not the initial deployment. They
tell us which parts of the system need special treatment.

| Metric                 | Assumption                         | Result                                    |
|------------------------|------------------------------------|-------------------------------------------|
| Link creation          | 100M / month                       | ~40 writes/s average, ~400/s peak         |
| Redirects              | 100 × creations                    | ~4,000 reads/s average, ~40,000/s peak    |
| Link storage           | ~500 B per link, kept 5 years      | 100M × 60 months × 500 B ≈ **3 TB**       |
| Click events           | 10B / month × ~100 B               | ~1 TB / month of raw events               |
| Cache                  | Hot 20% of daily traffic           | A few GB of Redis                         |
| Code space             | 7 characters of base62             | 62⁷ ≈ **3.5 trillion** codes              |

**What this tells us**

1. Reads dominate, so the redirect path must be served from a **cache**.
2. Click events are far larger than link data. They need **separate, batched
   storage** and a **retention policy**.
3. Seven base62 characters give enough space for random codes to rarely collide.

---

## 4. High-level architecture

```
                     ┌──────────────────────────┐
  Dashboard user ──▶ │  React SPA (static host) │
                     └────────────┬─────────────┘
                                  │ HTTPS  /api/v1/*
                                  ▼
  Link visitor ──▶  ┌──────────────────────────────────┐
   GET /{code}      │           FastAPI app            │
                    │                                  │
                    │  Redirect ── Links ── Auth ── …  │──────▶ Redis
                    │     │                            │        • link cache
                    │     │ publish ClickEvent         │        • rate limits
                    │     ▼                            │        • click stream
                    │  EventPublisher (interface)      │
                    │     │                            │
                    │     ▼                            │
                    │  Analytics worker (consumer)     │
                    └─────┬────────────────────────────┘
                          ▼
                     PostgreSQL
           users · links · clicks · daily stats · api keys
```

### Main components

| Component            | Responsibility                                                         |
|----------------------|------------------------------------------------------------------------|
| React SPA            | Login, dashboard, link management, analytics charts                    |
| FastAPI app          | REST API, redirect endpoint, auth, validation, rate limiting           |
| Redis                | Cache for code → URL lookups, rate-limit counters, click event stream  |
| Analytics worker     | Consumes click events in batches, enriches them and writes to Postgres |
| PostgreSQL           | Source of truth for users, links and analytics                         |

### Code layering (backend)

```
api/ (routers, HTTP concerns)
  └─▶ services/ (business rules — no HTTP, no SQL)
        └─▶ repositories/ (database access)
        └─▶ events/ (EventPublisher / EventConsumer interfaces + implementations)
```

**Why this layering:** business rules can be unit-tested without a web server
or database, and infrastructure (for example Redis Streams → Kafka) can be
swapped by adding a new implementation of an interface.

---

## 5. Short code generation

### Problem
Every link needs a unique, short, URL-safe code. Codes must **not be guessable**,
otherwise anyone could walk through every link (including private ones).

### Options considered

| Option | How it works | Pros | Cons |
|--------|--------------|------|------|
| A. Hash + truncate | `base62(sha256(url))[:7]` | Same URL → same code (dedup) | Collisions still need handling; one URL can't have separate links with separate analytics |
| B. Auto-increment counter → base62 | DB sequence `1, 2, 3…` encoded | No collisions, very short codes | **Enumerable** — trivial to scrape every link; the sequence is a single point of coordination |
| C. Counter + reversible obfuscation | Sequence passed through Sqids / a Feistel cipher | No collisions, looks random | More moving parts; the obfuscation key/alphabet can never change; still decodable in theory |
| **D. Random base62 + unique constraint + retry** | `secrets.choice` × 7, insert, retry on conflict | Simple, non-guessable, no coordination between instances | Very small collision chance, handled by retry |
| E. Key Generation Service | A separate service pre-generates unused codes | No collisions at write time, scales best | Another service to run and keep highly available |

### Decision: **D — random 7-character base62**

- Generated with Python's `secrets` module (a cryptographically secure random
  generator), so codes are unpredictable.
- The `links.code` column has a **unique index**. On a unique-violation we
  regenerate and retry, up to **3 attempts**, then return an error.
- **Collision math:** with 1 billion links stored, the chance a new random code
  collides is 10⁹ / 3.5×10¹² ≈ **0.03%**, and three consecutive collisions are
  practically impossible.

### Custom aliases
- Allowed characters `[A-Za-z0-9_-]`, length 3–30.
- Checked against a **reserved words** list (`api`, `admin`, `login`, `health`,
  `metrics`, `static`, …) so a user can never shadow an application route.
- Uniqueness enforced by the same unique index.

### When we would revisit
If write throughput grows to the point where retry rates or index contention
become measurable, move to **E (Key Generation Service)**.

---

## 6. Redirect strategy

### Options considered

| Status | Behaviour | Pros | Cons |
|--------|-----------|------|------|
| 301 Moved Permanently | Browser caches the redirect forever | Fewer requests to us | We lose analytics after the first visit; we can't edit, expire or deactivate the link |
| **302 Found** | Browser asks us every time | Every click is counted; edits/expiry work instantly | Every click costs us a request (mitigated by caching) |
| 307 Temporary Redirect | Like 302 but keeps the HTTP method | Strict semantics | No practical benefit for `GET` links |

### Decision: **302** with `Cache-Control: private, max-age=0`

Analytics, editing and expiry are core features, and all three require that
every click reaches our server. Bitly and similar services make the same choice.

### Redirect request flow

```
GET /{code}
  1. Look up "link:{code}" in Redis
       hit   → use cached link
       miss  → query Postgres → cache result (or a short-lived "not found" marker)
  2. Validate: is_active, not expired by date, click limit not reached
       invalid → 404 (not found / deactivated) or 410 Gone (expired)
  3. Publish ClickEvent (non-blocking, ~sub-millisecond)
  4. Return 302 Location: <target_url>
```

The redirect never waits on analytics processing.

---

## 7. Data storage and data model

### Options considered

| Option | Pros | Cons |
|--------|------|------|
| **PostgreSQL** | ACID, constraints, rich indexing, table partitioning, mature tooling, free managed tiers | Needs sharding at very large scale |
| MongoDB / document store | Flexible schema | We have relational data (users ↔ links ↔ keys) and want constraints |
| DynamoDB / Cassandra (key-value) | Massive horizontal scale for code → URL | Weak support for dashboard queries; vendor lock-in or operational weight |

### Decision: **PostgreSQL** as the source of truth

Our data is relational, we need unique constraints (codes, emails), and
Postgres handles our design-scale with partitioning and read replicas. Redis
covers the key-value hot path.

### Schema (simplified)

```
users
  id              UUID PK
  email           CITEXT UNIQUE
  password_hash   TEXT NULL          -- NULL for GitHub-only accounts
  github_id       BIGINT UNIQUE NULL
  is_active       BOOLEAN
  created_at      TIMESTAMPTZ

links
  id              BIGINT PK (identity)
  code            VARCHAR(30) UNIQUE
  target_url      TEXT
  owner_id        UUID FK → users
  title           TEXT NULL
  is_active       BOOLEAN
  expires_at      TIMESTAMPTZ NULL
  max_clicks      INTEGER NULL
  click_count     BIGINT DEFAULT 0
  created_at, updated_at
  INDEX (owner_id, created_at DESC)  -- dashboard listing

clicks                               -- raw events, 90-day retention
  id              BIGINT
  link_id         BIGINT
  occurred_at     TIMESTAMPTZ
  event_id        TEXT UNIQUE        -- idempotency for at-least-once delivery
  visitor_hash    TEXT               -- salted hash of IP + user agent
  country         CHAR(2) NULL
  device, browser, os  TEXT NULL
  referrer_domain TEXT NULL
  PARTITION BY RANGE (occurred_at)   -- one partition per month

link_daily_stats                     -- aggregates, kept forever
  link_id, day, clicks, unique_visitors       PK (link_id, day)
link_daily_breakdown
  link_id, day, dimension, value, clicks      PK (link_id, day, dimension, value)
  -- dimension ∈ {country, referrer, device, browser, os}

api_keys
  id, user_id, name, prefix UNIQUE, key_hash, last_used_at, revoked_at, created_at

refresh_tokens
  id, user_id, token_hash UNIQUE, family_id, expires_at, revoked_at, created_at
```

### Retention
Raw `clicks` are partitioned by month. Dropping a whole partition is instant and
avoids slow `DELETE`s, so a scheduled job drops partitions older than 90 days.
Aggregates in `link_daily_*` are kept forever because they are small.

---

## 8. Caching

### Options considered

| Strategy | Notes |
|----------|-------|
| **Cache-aside (lazy loading)** | Read from cache; on miss load from DB and populate. Only hot links occupy memory. |
| Write-through | Write to cache on every create. Fills memory with links that may never be clicked. |
| In-process LRU only | Fastest, but each instance has its own copy and invalidation across instances is hard. |

### Decision: **Cache-aside in Redis + explicit invalidation**

- Key `link:{code}` → small JSON (target URL, active flag, expiry, max clicks).
- **TTL** of 24 h, refreshed on read, so memory follows real traffic.
- **Negative caching:** unknown codes are cached as "not found" for 60 s so bots
  probing random codes can't hammer Postgres.
- **Invalidation:** any update or delete removes `link:{code}` immediately.
- **Click limits:** `max_clicks` checks use an atomic Redis `INCR` counter;
  the worker periodically syncs `click_count` back to Postgres.
- **Redis down?** The redirect path falls back to Postgres. Slower, but it keeps
  working (graceful degradation).

---

## 9. Analytics pipeline

### Problem
Every redirect produces an event. Writing each one synchronously to Postgres
would add latency to the hot path and create heavy write load.

### Options considered

| Option | Pros | Cons |
|--------|------|------|
| Synchronous INSERT per click | Simplest | Adds latency to redirects; poor write efficiency |
| FastAPI `BackgroundTasks` | No extra infra | Events lost on crash/restart; no batching; no replay |
| Celery / RQ / ARQ task queue | Mature, retries | Task-per-click is heavy; not a natural event log |
| **Redis Streams with consumer groups** | Durable-ish log, consumer groups, acks, replay, batching; Redis is already in our stack | Bounded by Redis memory; not as durable as Kafka |
| Kafka (or Redpanda) | Industry standard event log, huge throughput, long retention | Operational weight; no reasonable free tier |

### Decision: **Redis Streams now, Kafka later — behind an interface**

```python
class EventPublisher(Protocol):
    async def publish(self, event: ClickEvent) -> None: ...

class EventConsumer(Protocol):
    async def consume(self, handler: Callable[[list[ClickEvent]], Awaitable[None]]) -> None: ...
```

`RedisStreamPublisher` / `RedisStreamConsumer` are the first implementations.
Moving to Kafka means adding `KafkaPublisher` / `KafkaConsumer` and changing a
setting. Business code does not change. Redis Streams and Kafka share the same
concepts (append-only log, consumer groups, offsets/acks), which makes this
migration natural.

### Flow

```
redirect ── XADD clicks * {event_id, code, link_id, ts, ip_hash, ua, referrer}
                         (stream capped with MAXLEN ~ to bound memory)

worker ── XREADGROUP GROUP analytics … COUNT 500 BLOCK 1000
       ── enrich:  user agent → device / browser / OS   (ua-parser)
                   IP → country                         (local MaxMind GeoLite2 DB)
       ── bulk INSERT clicks … ON CONFLICT (event_id) DO NOTHING
       ── UPSERT link_daily_stats / link_daily_breakdown
       ── XACK
```

- **Delivery guarantee:** at-least-once. The `event_id` unique constraint
  makes processing idempotent, so redelivered events are not double counted.
- **Crash recovery:** unacknowledged messages stay in the pending list and are
  re-claimed (`XAUTOCLAIM`) by the worker on restart.
- **Dashboard queries** read the daily aggregate tables, never raw clicks, so
  charts stay fast regardless of traffic.
- **Unique visitors:** counted by distinct `visitor_hash` per day. At larger
  scale, Redis HyperLogLog gives approximate counts in constant memory.
- **Privacy:** the raw IP is used only in memory to derive country and hash; it
  is never written to disk. The hash salt rotates daily so visitors can't be
  tracked across days.

---

## 10. Authentication and authorization

### Decision: **login required to create links**

| Option | Pros | Cons |
|--------|------|------|
| Anonymous creation (rate limit + CAPTCHA) | Lowest friction | Primary channel for spam/phishing abuse; hard to moderate; risky on a free tier |
| **Login required** | Every link has an owner; abuse is traceable and bannable; simpler rate limiting | Slight friction for first-time users |

Redirects (`GET /{code}`) are of course public.

### Session strategy

| Option | Pros | Cons |
|--------|------|------|
| Server-side sessions (cookie + session store) | Easy revocation | Session store lookup on every request |
| JWT in `localStorage` | Simple | Readable by any XSS payload |
| **Short-lived access JWT (memory) + rotating refresh token (httpOnly cookie)** | Stateless API auth; refresh token not reachable by JavaScript; revocable | More moving parts |

**Decision:** access JWT valid for **15 minutes**, kept in memory by the SPA and
sent as `Authorization: Bearer`. The refresh token is an opaque random string in
an `httpOnly; Secure; SameSite` cookie, stored **hashed** in the database and
**rotated on every use**. If an already used refresh token is presented again
(a sign of theft), the whole token family is revoked.

### Other auth details
- **Password hashing:** Argon2id (current OWASP recommendation).
- **GitHub OAuth:** authorization-code flow with a `state` parameter (CSRF
  protection). Accounts are linked by verified email.
- **API keys:** format `snp_<prefix>_<secret>`, shown once at creation. Only a
  SHA-256 hash is stored; lookup is by `prefix`. Keys can be revoked.
- **Authorization:** users can only read or modify their own links. Requests for
  another user's link return `404` (not `403`) so link existence isn't leaked.

---

## 11. Security and abuse prevention

| Threat | Mitigation |
|--------|------------|
| Phishing / malware links | Google Safe Browsing lookup on create and on target update; links can be deactivated |
| Fake account farming | Cloudflare Turnstile CAPTCHA (free) on registration |
| Brute force / flooding | Redis sliding-window rate limits per IP (auth endpoints), per user and per API key; `429` + `Retry-After` |
| Redirect loops / chaining | Reject targets on our own domain and on a list of known shortener domains |
| Dangerous URL schemes | Only `http` and `https` allowed (`javascript:`, `data:`, `file:` rejected); max length 2048 |
| Link enumeration | Random codes + rate-limited 404s + negative caching |
| XSS | React escaping, strict Content-Security-Policy, no `dangerouslySetInnerHTML` |
| CSRF | Bearer tokens for API calls; refresh cookie is `SameSite` and scoped to the refresh path |
| Credential stuffing | Rate limits on login, generic error messages, Argon2id |
| Secret leakage | Settings from environment variables, `.env` git-ignored, secret scanning in CI, no secrets in logs |
| Dependency vulnerabilities | Dependabot, `pip-audit` / `npm audit` in CI |
| Transport | HTTPS only, HSTS header |

---

## 12. API design

### Style decision

| Option | Pros | Cons |
|--------|------|------|
| **REST + JSON, versioned (`/api/v1`)** | Simple, cacheable, great tooling, FastAPI generates OpenAPI docs | Possible over/under-fetching |
| GraphQL | Flexible queries | Overkill for a small resource model; harder caching and rate limiting |
| gRPC | Fast, typed | Not browser friendly |

### Endpoints

```
Auth
  POST   /api/v1/auth/register
  POST   /api/v1/auth/login
  POST   /api/v1/auth/refresh
  POST   /api/v1/auth/logout
  GET    /api/v1/auth/github/login
  GET    /api/v1/auth/github/callback
  GET    /api/v1/me

Links
  POST   /api/v1/links                       (supports Idempotency-Key header)
  GET    /api/v1/links?cursor=&limit=&q=
  GET    /api/v1/links/{id}
  PATCH  /api/v1/links/{id}
  DELETE /api/v1/links/{id}
  GET    /api/v1/links/{id}/stats?from=&to=
  GET    /api/v1/links/{id}/qr?format=png|svg

API keys
  POST   /api/v1/api-keys
  GET    /api/v1/api-keys
  DELETE /api/v1/api-keys/{id}

Public / ops
  GET    /{code}          → 302 redirect
  GET    /healthz         → process is alive
  GET    /readyz          → dependencies (DB, Redis) reachable
  GET    /metrics         → Prometheus metrics
```

### Conventions
- **Errors:** RFC 7807 `application/problem+json`
  (`type`, `title`, `status`, `detail`, `instance`) so every error has the
  same shape.
- **Pagination:** cursor-based (keyset on `created_at, id`). Unlike
  `OFFSET`, it stays fast on large tables and doesn't skip/duplicate rows when
  data changes between pages.
- **Idempotency:** `POST /links` accepts an `Idempotency-Key` header; the
  response is stored in Redis for 24 h so client retries don't create
  duplicate links.
- **Validation:** Pydantic models at the edge; invalid input → `422` with
  field-level details.

---

## 13. Technology choices

### Backend

| Concern | Choice | Why |
|---------|--------|-----|
| Language / framework | Python 3.13, **FastAPI** | Async, type-hint driven, automatic OpenAPI docs |
| Validation / settings | Pydantic v2, pydantic-settings | Fast validation; typed config from environment |
| ORM / DB driver | SQLAlchemy 2.0 (async) + asyncpg | Mature, typed 2.0 API, async support |
| Migrations | Alembic | Standard for SQLAlchemy, versioned schema changes |
| Redis client | redis-py (asyncio) | Official client, supports Streams |
| Dependency management | **uv** | Very fast, lockfile for reproducible installs |
| Lint / format / types | Ruff, mypy (strict) | One fast tool for lint + format; strict typing catches bugs early |
| Tests | pytest, pytest-asyncio, httpx, **testcontainers** | Integration tests run against real Postgres/Redis instead of mocks |
| Logging | structlog (JSON) | Structured, machine-parseable logs with request IDs |

### Frontend

| Concern | Choice | Why |
|---------|--------|-----|
| Build tool | Vite | Fast dev server and builds |
| Language | React 18 + **TypeScript (strict)** | Type safety across API boundaries |
| Routing | React Router | Standard, supports protected routes |
| Server state | TanStack Query | Caching, retries, request deduplication |
| Forms / validation | react-hook-form + zod | Performant forms, schema validation shared with types |
| UI | Tailwind CSS + shadcn/ui | Accessible components we own and can customise |
| Charts | Recharts | Simple React charting for analytics |
| Tests | Vitest + Testing Library, Playwright (E2E) | Unit/component tests + real-browser flows |

### Infrastructure / tooling
Docker (multi-stage images), docker-compose for local development, GitHub
Actions for CI/CD, pre-commit hooks, Dependabot.

---

## 14. Observability, testing and delivery

### Observability
- **Logs:** JSON via structlog; every request gets a `request_id` (from the
  `X-Request-ID` header or generated) included in all log lines and responses.
- **Metrics:** Prometheus `/metrics` — request rate/latency/errors per route,
  cache hit ratio, redirect count, stream lag, worker batch size and failures.
- **Errors:** Sentry for backend and frontend exceptions.
- **Health:** `/healthz` (liveness) and `/readyz` (readiness, checks DB and Redis).

### Testing strategy

| Layer | Tooling | What it covers |
|-------|---------|----------------|
| Unit | pytest, Vitest | Services, code generation, URL validation, components |
| Integration | pytest + testcontainers | Repositories, API endpoints against real Postgres/Redis |
| End-to-end | Playwright | Register → create link → redirect → see analytics |
| Load | k6 | Redirect throughput and latency under load |

### Delivery
- **Conventional Commits** (`feat:`, `fix:`, `chore:` …) in small, reviewable commits.
- **CI** on every push/PR: lint, type-check, tests, build Docker images,
  dependency audit.
- **CD** on `main`: deploy backend and frontend automatically after CI passes.
- **Migrations** run as a release step before the new version serves traffic.

---

## 15. Deployment (free tier)

The project has **no hosting budget**, so the first deployment uses free tiers.
Free-tier limits change often; verify them at deployment time.

| Component | Planned host | Main limitation |
|-----------|--------------|-----------------|
| Frontend (static) | Cloudflare Pages or Vercel | — |
| Backend (FastAPI) | Render free web service (alternative: Koyeb) | Sleeps when idle → **cold start of tens of seconds** |
| PostgreSQL | Neon free tier | Storage cap; compute suspends when idle |
| Redis | Upstash free tier | Monthly command cap → tune worker polling |
| Error tracking | Sentry free plan | Event quota |

### Known trade-offs (documented on purpose)
- **Worker runs inside the API process.** Free tiers don't offer background
  workers, so the analytics consumer starts in FastAPI's `lifespan`. A config
  flag (`RUN_WORKER_IN_PROCESS`) lets it run as a separate process when
  resources allow. The code is identical either way.
- **Cold starts.** The first redirect after idle is slow. Fixes when budget
  allows: an always-on instance, or edge redirects (see §16).
- **Short link domain.** Initially links use the backend's platform subdomain.
  Alternatively, the frontend host can proxy `/{code}` to the backend so links
  use the nicer frontend domain.

---

## 16. Scaling beyond the free tier

How the design grows toward the targets in §3 without a rewrite:

1. **Stateless API** → run N replicas behind a load balancer.
2. **Database** → read replicas for dashboard queries; shard `links` by
   hash of `code` at very large scale.
3. **Cache** → Redis Cluster; add an in-process LRU in front of Redis for the
   hottest links.
4. **Edge redirects** → Cloudflare Workers + KV serve popular links from the
   CDN, with clicks forwarded to the event pipeline.
5. **Analytics** → replace Redis Streams with Kafka; store raw events in a
   columnar database (ClickHouse) and keep Postgres for links and aggregates.
6. **Code generation** → move to a Key Generation Service if random-code
   retries become measurable.
7. **Worker** → run as separate, horizontally scaled consumers in the same
   consumer group.

---

## 17. Open questions and future work

- Custom domains per user.
- Password-protected links.
- Teams / shared workspaces.
- Link previews (Open Graph metadata fetching) — needs SSRF protection.
- Bulk link creation via CSV upload.
- Account deletion and data export (GDPR).

---

## 18. Changelog

| Date       | Change                                                                 |
|------------|------------------------------------------------------------------------|
| 2026-10-18 | Initial design: random codes, login-required creation, Redis Streams analytics, 90-day raw retention |
