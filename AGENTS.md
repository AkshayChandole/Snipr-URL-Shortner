# AGENTS.md

Instructions for AI coding agents (Claude Code, Cursor, GitHub Copilot, …)
working on this repository. Humans are welcome to read it too.

## Project

**Snipr** is a production-grade URL shortener built as a portfolio project:
FastAPI backend, React + TypeScript frontend, PostgreSQL, Redis. Treat it as a
real production system, not a tutorial.

## Read these first

| File | What it tells you |
|------|-------------------|
| [`docs/roadmap.md`](docs/roadmap.md) | **Current status and the next commit to make.** Start here. |
| [`docs/design.md`](docs/design.md) | System design: every major decision, the options considered and why |
| `backend/README.md`, `frontend/README.md` | How to run, test and lint each part |

## Working rules (mandatory)

1. **One commit at a time.** Make a single small, focused commit, then explain
   it to the user: files changed, what the code does, why it is written that
   way and how it was verified. **Stop and wait for the user's review** before
   starting the next commit. Never batch several commits in one go.
2. **Never push** unless the user explicitly asks.
3. **No AI attribution.** Do not add `Co-Authored-By` trailers or any other
   AI/assistant attribution to commits or pull requests.
4. **Conventional Commits:** `feat:`, `fix:`, `docs:`, `chore:`, `ci:`,
   `build:`, `test:`, `refactor:`, with a scope where helpful
   (`feat(backend): …`). Subject line in imperative mood, ≤ 72 characters.
5. **Keep `docs/design.md` current.** If a design decision changes or a new one
   is made, update the relevant section (options, decision, rationale) **and**
   add a dated row to its Changelog, in the same commit as the code.
6. **Keep `docs/roadmap.md` current.** Every commit ticks off its roadmap item
   and updates the "Current status" section, so the next agent knows where
   things stand.
7. **Every commit leaves the build green:** lint, format, type checks and tests
   pass for the part you touched (see Commands below).
8. **Free tier only.** There is no hosting budget; don't introduce services
   that require payment.

## Repository layout

```
backend/     FastAPI app (Python 3.13, uv)
  app/       api/ → services/ → repositories/ (layered; see design.md §4)
  tests/
frontend/    React 19 + TypeScript + Vite
docs/        design.md, roadmap.md
.github/     CI workflow, Dependabot
docker-compose.yml   local PostgreSQL + Redis
```

## Commands

```bash
# Infrastructure
docker compose up -d

# Backend (run inside backend/)
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy app tests
uv run pytest --cov
uv run uvicorn app.main:app --reload

# Frontend (run inside frontend/)
npm ci
npm run lint && npm run format:check
npm run build          # also type-checks

# All git hooks
pre-commit run --all-files
```

## Code conventions

### Backend
- Layering: routers in `app/api` handle HTTP only; business rules live in
  `app/services` (no HTTP, no SQL); database access in `app/repositories`.
- Fully typed; **mypy strict** must pass. Pydantic models at API boundaries.
- Async all the way (SQLAlchemy async, redis asyncio). No blocking I/O in
  request handlers.
- Errors are returned as RFC 7807 `application/problem+json`.
- Tests: unit tests for pure logic; integration tests against real Postgres /
  Redis via testcontainers. No mocking of the database.
- pytest treats warnings as errors: fix them, don't silence them.

### Frontend
- TypeScript strict (incl. `noUncheckedIndexedAccess`); no `any`.
- Oxlint for linting, Prettier for formatting.

### Dependencies
- Backend: add with `uv add` (commit `uv.lock`). Frontend: `npm install`
  (commit `package-lock.json`). Both are pinned to the public registries.
- Don't accept major-version bumps of the `postgres` / `redis` images or
  `@types/node` without updating the matching runtime (see design.md and
  `.github/dependabot.yml`).

## Environment notes

- Some networks intercept TLS. If `uv` fails with certificate errors, run it
  with `UV_SYSTEM_CERTS=1`.
- If the pre-commit hook can't install its tools because a global pip config
  points at an unreachable private index, prefix the commit with
  `PIP_INDEX_URL=https://pypi.org/simple`.
- Never commit secrets. `.env` is git-ignored; document new settings in
  `.env.example`.
