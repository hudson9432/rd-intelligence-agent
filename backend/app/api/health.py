"""Service health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Stable response contract for service health checks."""

    status: Literal["ok"]
    service: Literal["rd-intelligence-agent-backend"]


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return a lightweight liveness response."""

    return HealthResponse(
        status="ok",
        service="rd-intelligence-agent-backend",
    )
