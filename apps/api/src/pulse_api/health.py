"""Liveness and readiness endpoints."""

import logging
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from pulse_api.config import Settings, get_settings
from pulse_api.db import check_database
from pulse_api.redis_client import check_redis

router = APIRouter()
logger = logging.getLogger(__name__)
_settings = Depends(get_settings)

CheckState = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, CheckState]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
def ready(settings: Settings = _settings) -> JSONResponse:
    checks: dict[str, CheckState] = {}
    checks["database"] = _run_check("database", lambda: check_database(settings.database_url))
    checks["redis"] = _run_check("redis", lambda: check_redis(settings.redis_url))
    available = all(state == "ok" for state in checks.values())
    body = ReadyResponse(
        status="ok" if available else "unavailable",
        checks=checks,
    )
    return JSONResponse(status_code=200 if available else 503, content=body.model_dump())


def _run_check(name: str, check: Callable[[], None]) -> CheckState:
    try:
        check()
    except Exception:
        logger.error("%s readiness check failed", name)
        return "error"
    return "ok"
