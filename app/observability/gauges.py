"""Background coroutine that refreshes Prometheus gauges from DB state.

Currently only `proline_quarantine_pending` -- count of quarantine_terms whose
review state is still pending. Polled every 30 s; failures are logged but do
not crash the app.
"""

from __future__ import annotations

import asyncio
import os

from sqlalchemy import text

from app.observability.logging import get_logger
from app.observability.metrics import METRICS


log = get_logger(__name__)

_DEFAULT_INTERVAL_S = 30.0


async def gauge_refresh_loop(interval_s: float | None = None) -> None:
    """Long-running task: refreshes registered gauges. Cancelled at shutdown."""
    interval = interval_s or float(os.getenv("DASHBOARD_GAUGE_INTERVAL_S", _DEFAULT_INTERVAL_S))
    log.info("gauge_loop_started", interval_s=interval)
    try:
        while True:
            try:
                await _refresh_once()
            except Exception as e:  # noqa: BLE001
                log.warning("gauge_refresh_failed", error=str(e))
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        log.info("gauge_loop_stopped")
        raise


async def _refresh_once() -> None:
    """Run one snapshot pass; safe to call directly in tests."""
    from app.deps import _SessionLocal

    if _SessionLocal is None:
        # No DB engine -- skip silently (matches the boot-without-DB story).
        return

    # Run blocking SA call in default executor so the event loop stays free.
    loop = asyncio.get_running_loop()
    pending = await loop.run_in_executor(None, _query_pending)
    METRICS.quarantine_pending.set(float(pending))


def _query_pending() -> int:
    from app.deps import _SessionLocal

    assert _SessionLocal is not None
    with _SessionLocal() as db:
        # Keep the query defensive: the table might not exist on lite/older
        # databases. Return 0 in that case (with a debug log).
        try:
            row = db.execute(
                text(
                    "SELECT COUNT(*) FROM quarantine_terms "
                    "WHERE decision = 'pending'"
                )
            ).scalar_one()
            return int(row or 0)
        except Exception as e:  # noqa: BLE001
            log.debug("quarantine_query_unsupported", error=str(e))
            return 0
