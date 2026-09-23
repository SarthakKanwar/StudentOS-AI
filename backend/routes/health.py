"""Liveness endpoint. No auth (architecture.md section 9).

Deliberately does not touch Foundry, Supabase, or any other dependency: a
liveness probe that calls downstream services turns their outage into this
service's outage, and makes the response non-deterministic.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend import SERVICE_NAME, __version__

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=__version__)
