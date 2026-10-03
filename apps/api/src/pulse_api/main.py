"""FastAPI application entrypoint."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.responses import Response

from pulse_api import __version__
from pulse_api.config import get_settings
from pulse_api.health import router as health_router
from pulse_api.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("application started", extra={"app_env": settings.app_env, "version": __version__})
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Pulse API", version=__version__, lifespan=lifespan)
    app.include_router(health_router)

    @app.middleware("http")
    async def log_request(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        logger.info(
            "request completed",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
            },
        )
        return response

    return app


app = create_app()
