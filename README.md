# Snipr

[![CI](https://github.com/AkshayChandole/Snipr/actions/workflows/ci.yml/badge.svg)](https://github.com/AkshayChandole/Snipr/actions/workflows/ci.yml)

A production-grade URL shortener with user accounts, custom aliases, link
expiry, click analytics, QR codes and API keys.

- **Backend:** Python, FastAPI, PostgreSQL, Redis
- **Frontend:** React, TypeScript, Vite, Tailwind CSS

> 🚧 Work in progress. See [`docs/design.md`](docs/design.md) for the full
> system design: options considered and why each decision was made.

## Repository layout

```
backend/    FastAPI application
frontend/   React single-page application
docs/       System design and documentation
```

## Local development

Prerequisites: [Docker](https://docs.docker.com/get-docker/), [uv](https://docs.astral.sh/uv/), Node.js 24 (see `frontend/.nvmrc`).

```bash
cp .env.example .env
docker compose up -d                 # PostgreSQL + Redis
```

Then follow [`backend/README.md`](backend/README.md) and
[`frontend/README.md`](frontend/README.md).

## License

[MIT](LICENSE)
