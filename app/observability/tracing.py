"""OpenTelemetry SDK init -- safe defaults, no collector required for dev.

OTEL_TRACES_EXPORTER controls the exporter:
  - 'none'  (default in dev): no spans exported, instrumentation still runs
            so structlog gets trace_id / span_id correlation.
  - 'otlp': OTLP/gRPC to OTEL_EXPORTER_OTLP_ENDPOINT (default :4317).
  - 'console': dump spans to stdout (debugging only).
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)


_INITIALIZED = False


def configure_tracing(service_name: str = "proline-dashboard") -> None:
    """Idempotent. Safe to call from FastAPI startup."""
    global _INITIALIZED
    if _INITIALIZED:
        return

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", service_name),
            "service.version": os.getenv("APP_VERSION", "0.0.0"),
            "deployment.environment": os.getenv("DEPLOY_ENV", "dev"),
        }
    )
    provider = TracerProvider(resource=resource)

    exporter_kind = os.getenv("OTEL_TRACES_EXPORTER", "none").lower()
    if exporter_kind == "console":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    elif exporter_kind == "otlp":
        # Lazy import: OTLP transport pulls grpcio (~6 MB), keep it optional.
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore
            OTLPSpanExporter,
        )
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    # 'none' -> no processor; spans are still created so trace_id propagates.

    trace.set_tracer_provider(provider)
    _INITIALIZED = True


def instrument_app(app, engine=None) -> None:
    """Auto-instrument FastAPI + SQLAlchemy. Call AFTER configure_tracing()."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # type: ignore

    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz,metrics")

    if engine is not None:
        from opentelemetry.instrumentation.sqlalchemy import (  # type: ignore
            SQLAlchemyInstrumentor,
        )
        SQLAlchemyInstrumentor().instrument(engine=engine)
