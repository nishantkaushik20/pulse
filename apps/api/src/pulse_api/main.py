"""FastAPI application entrypoint."""

import logging
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from pulse_api import __version__
from pulse_api.config import get_settings
from pulse_api.errors import DomainError
from pulse_api.gmail.routes import router as gmail_router
from pulse_api.health import router as health_router
from pulse_api.logging import configure_logging
from pulse_api.routes import customer_router, identity_router, operations_router

logger = logging.getLogger(__name__)
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("application started", extra={"app_env": settings.app_env, "version": __version__})
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Pulse API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_web_origin()],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(customer_router)
    app.include_router(operations_router)
    app.include_router(gmail_router)

    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.middleware("http")
    async def log_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = _request_id(request.headers.get("x-request-id"))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
            },
        )
        return response

    return app


def _request_id(header: str | None) -> str:
    if header and _REQUEST_ID.fullmatch(header):
        return header
    return str(uuid4())


def _web_origin() -> str:
    raw = os.environ.get("WEB_APP_URL", "http://localhost:3000").strip().rstrip("/")
    return raw or "http://localhost:3000"


app = create_app()
