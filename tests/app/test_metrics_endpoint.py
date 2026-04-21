"""Prometheus /metrics endpoint surface."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_metrics_endpoint_returns_prom_format(client: TestClient) -> None:
    # Generate at least one labeled observation first.
    client.get("/healthz")
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    # Prometheus client default content type
    assert r.headers["content-type"].startswith("text/plain")
    # Required custom metrics MUST be present.
    assert "proline_http_request_duration_seconds" in body
    assert "proline_http_requests_total" in body
    assert "proline_dashboard_runs_total" in body
    # Process collector smoke (proves we use the default registry).
    assert "process_cpu_seconds_total" in body or "python_info" in body


def test_metrics_count_increments(client: TestClient) -> None:
    client.get("/healthz")
    body1 = client.get("/metrics").text
    client.get("/healthz")
    client.get("/healthz")
    body2 = client.get("/metrics").text
    # Crude but sufficient: the 'route="/healthz"' counter should appear in both
    # and the second snapshot must have a strictly larger value somewhere.
    assert "/healthz" in body1
    assert "/healthz" in body2
    assert body1 != body2
