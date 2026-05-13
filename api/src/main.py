"""FastAPI application factory and ASGI entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.src.config import settings
from api.src.middleware.logging import RequestContextMiddleware, configure_logging
from api.src.routes import calls, carrier, health, loads, metrics, negotiate, stream


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Inbound Carrier Sales API",
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(carrier.router, prefix="/api/v1")
    app.include_router(loads.router, prefix="/api/v1")
    app.include_router(negotiate.router, prefix="/api/v1")
    app.include_router(calls.router, prefix="/api/v1")
    app.include_router(metrics.router, prefix="/api/v1")
    # Stream router is registered separately so its query-param auth isn't
    # shadowed by the calls router's X-API-Key header dependency.
    app.include_router(stream.router, prefix="/api/v1")

    return app


app = create_app()
