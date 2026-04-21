"""Observability subpackage -- structlog + OpenTelemetry + Prometheus.

See ADR-006 for the why. Each module is independently importable so that
tests can stub one without pulling the others.
"""
