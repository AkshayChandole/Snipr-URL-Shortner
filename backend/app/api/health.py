"""Operational endpoints used by the hosting platform and monitoring."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["ops"])


class HealthResponse(BaseModel):
    status: Literal["ok"]


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    """Liveness probe: the process is up and serving requests.

    Deliberately checks no dependencies. A database outage should mark the
    instance *not ready* (see `/readyz`, added later), not trigger a restart.
    """
    return HealthResponse(status="ok")
