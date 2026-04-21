"""Prometheus metric registry + helpers.

Convention (ADR-006):
  - histograms end in _seconds
  - counters end in _total
  - namespace prefix proline_ for all custom metrics
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest


# Module-level singletons -- registered to prometheus_client's default REGISTRY
# at first import. Earlier attempts wrapped these in a class defined inside a
# function ("build_metrics()") so that tests could pass a custom registry,
# but that pattern silently failed to register the metrics on the global
# REGISTRY when build_metrics() was called at import time -- /metrics
# returned only python_gc + python_info. Module-level constants avoid that
# class-scope timing trap entirely.

http_request_duration_seconds = Histogram(
    "proline_http_request_duration_seconds",
    "HTTP request latency by route and method.",
    labelnames=("method", "route", "status"),
    # Buckets tuned for an interactive dashboard backend (target P95 < 500ms).
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

http_requests_total = Counter(
    "proline_http_requests_total",
    "HTTP request count by route, method, status.",
    labelnames=("method", "route", "status"),
)

dashboard_runs_total = Counter(
    "proline_dashboard_runs_total",
    "Dashboard run lifecycle events.",
    labelnames=("event",),  # event in {created, fetched, listed}
)

quarantine_pending = Gauge(
    "proline_quarantine_pending",
    "Quarantine terms awaiting reviewer decision.",
)


class _MetricsNamespace:
    """Attribute-style accessor used by middleware and routers."""

    http_request_duration_seconds = http_request_duration_seconds
    http_requests_total = http_requests_total
    dashboard_runs_total = dashboard_runs_total
    quarantine_pending = quarantine_pending


METRICS = _MetricsNamespace()


def render_metrics() -> bytes:
    """Body for the /metrics endpoint."""
    return generate_latest()
