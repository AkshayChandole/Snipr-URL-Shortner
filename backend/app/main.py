"""Application entry point.

`create_app()` is an application factory: tests build a fresh app per test
session, and the ASGI server imports the module-level `app` instance.
"""

from fastapi import FastAPI

from app.api.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Snipr API",
        version="0.1.0",
        description="Production-grade URL shortener.",
    )
    app.include_router(health_router)
    return app


app = create_app()
