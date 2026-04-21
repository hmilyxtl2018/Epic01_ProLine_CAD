"""Dashboard backend FastAPI entry point.

Wires:
  - structlog (JSON in prod, console in dev)
  - OpenTelemetry SDK + FastAPI/SQLAlchemy auto-instrumentation
  - Prometheus /metrics
  - Request-context middleware (request_id / mcp_context_id / access log)
  - Unified error envelope handlers
  - Routers: health, metrics, dashboard_runs
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.deps import dispose_engine, init_engine
from app.errors import install_exception_handlers
from app.observability.gauges import gauge_refresh_loop
from app.observability.logging import configure_logging, get_logger
from app.observability.metrics import METRICS  # noqa: F401  (forces registration)
from app.observability.middleware import RequestContextMiddleware
from app.observability.tracing import configure_tracing, instrument_app
from app.queue import close_arq_pool, close_pubsub_redis
from app.routers import auth, dashboard_runs, health, metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("app.startup")
    configure_tracing("proline-dashboard")
    # DB engine is optional at boot when POSTGRES_DSN is unset (allows
    # `uvicorn app.main:app` for OpenAPI inspection without a DB). Routes
    # that need it will fail at request time with a clean error.
    engine = None
    try:
        engine = init_engine()
    except RuntimeError as e:
        log.warning("db_init_skipped", reason=str(e))
    instrument_app(app, engine=engine)

    # Gauge refresh loop (DB-backed metrics). Disabled in tests via
    # DASHBOARD_DISABLE_GAUGE_LOOP=1 to keep test runtimes deterministic.
    gauge_task: asyncio.Task | None = None
    if os.getenv("DASHBOARD_DISABLE_GAUGE_LOOP", "").strip() not in ("1", "true", "True"):
        gauge_task = asyncio.create_task(gauge_refresh_loop())

    log.info("app_started", env=os.getenv("DEPLOY_ENV", "dev"))
    try:
        yield
    finally:
        if gauge_task is not None:
            gauge_task.cancel()
            try:
                await gauge_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        await close_arq_pool()
        await close_pubsub_redis()
        dispose_engine()
        log.info("app_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ProLine CAD — Dashboard Backend",
        version=os.getenv("APP_VERSION", "0.1.0-m1"),
        description=(
            "BFF for the ParseAgent Dashboard. "
            "Aggregates runs, quality, quarantine, and ops metrics."
        ),
        lifespan=lifespan,
    )
    # Middleware order: request-context OUTERMOST so it sees final status code.
    app.add_middleware(RequestContextMiddleware)
    install_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(dashboard_runs.router)
    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover -- manual run path
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("APP_RELOAD", "true").lower() in ("1", "true", "yes"),
    )
