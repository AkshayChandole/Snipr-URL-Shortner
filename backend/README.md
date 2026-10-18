# Snipr backend

FastAPI service for the Snipr URL shortener.

## Requirements

- [uv](https://docs.astral.sh/uv/) (installs Python 3.13 automatically)

## Common commands

```bash
uv sync                                    # install dependencies into .venv
uv run uvicorn app.main:app --reload       # dev server on http://localhost:8000
uv run pytest                              # run tests
```

Interactive API docs are served at http://localhost:8000/docs.
