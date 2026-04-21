"""Queue + pub/sub abstraction.

Backends:
    - "arq"    -- production: arq + Redis. Workers run as `arq app.queue.WorkerSettings`.
    - "inline" -- dev/tests: Starlette BackgroundTasks; pub/sub is a no-op.

Selection:
    DASHBOARD_QUEUE_BACKEND=arq|inline   (default: inline if REDIS_URL unset, else arq)
    REDIS_URL=redis://localhost:6379

This module exports a single coroutine `enqueue_parse_run(run_id)` and a single
async generator `subscribe_run_events(run_id)` used by the WS endpoint.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.observability.logging import get_logger


log = get_logger(__name__)

RUN_EVENTS_CHANNEL_PREFIX = "proline.runs."


def _backend() -> str:
    explicit = os.getenv("DASHBOARD_QUEUE_BACKEND", "").strip().lower()
    if explicit in ("arq", "inline"):
        return explicit
    return "arq" if os.getenv("REDIS_URL") else "inline"


def _redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://localhost:6379")


# ── arq glue (lazy imports so inline mode doesn't pay the cost) ────────

_arq_pool = None  # arq.connections.ArqRedis


async def _get_arq_pool():
    global _arq_pool
    if _arq_pool is not None:
        return _arq_pool
    from arq import create_pool
    from arq.connections import RedisSettings

    settings = RedisSettings.from_dsn(_redis_url())
    _arq_pool = await create_pool(settings)
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.aclose()
        _arq_pool = None


# ── Pub/sub Redis (separate from arq's pool to keep conn semantics clean) ──

_pubsub_redis = None  # redis.asyncio.Redis


async def _get_pubsub_redis():
    global _pubsub_redis
    if _pubsub_redis is not None:
        return _pubsub_redis
    from redis import asyncio as aioredis  # arq pulls redis-py in

    _pubsub_redis = aioredis.from_url(_redis_url(), decode_responses=True)
    return _pubsub_redis


async def close_pubsub_redis() -> None:
    global _pubsub_redis
    if _pubsub_redis is not None:
        await _pubsub_redis.aclose()
        _pubsub_redis = None


async def publish_run_event(run_id: str, event: dict) -> None:
    """Worker-side: notify subscribers of a status change.

    Inline backend swallows the call -- callers fall back to polling.
    """
    if _backend() != "arq":
        return
    try:
        r = await _get_pubsub_redis()
        await r.publish(RUN_EVENTS_CHANNEL_PREFIX + run_id, json.dumps(event))
    except Exception as e:  # noqa: BLE001
        log.warning("publish_run_event_failed", run_id=run_id, error=str(e))


@asynccontextmanager
async def subscribe_run_events(run_id: str) -> AsyncIterator["asyncio.Queue[dict]"]:
    """WS-side context manager: yields a queue receiving published events.

    Falls back to an empty queue (no events) when backend is inline -- the
    WS handler then degrades to polling.
    """
    if _backend() != "arq":
        q: "asyncio.Queue[dict]" = asyncio.Queue()
        yield q
        return

    r = await _get_pubsub_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(RUN_EVENTS_CHANNEL_PREFIX + run_id)
    out: "asyncio.Queue[dict]" = asyncio.Queue()

    async def _pump():
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    out.put_nowait(json.loads(msg["data"]))
                except (ValueError, KeyError):
                    continue
        except asyncio.CancelledError:
            return

    pump_task = asyncio.create_task(_pump())
    try:
        yield out
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        try:
            await pubsub.unsubscribe(RUN_EVENTS_CHANNEL_PREFIX + run_id)
            await pubsub.aclose()
        except Exception:  # noqa: BLE001
            pass


# ── Public enqueue API ─────────────────────────────────────────────────

async def enqueue_parse_run(run_id: str, *, fallback_background_tasks=None) -> str:
    """Schedule the worker for a run.

    With arq backend: returns the arq job_id.
    With inline backend: schedules via the provided BackgroundTasks instance
    (must come from the FastAPI request) and returns 'inline'. If neither is
    available, returns 'skipped'.
    """
    backend = _backend()
    if backend == "arq":
        pool = await _get_arq_pool()
        job = await pool.enqueue_job("process_run", run_id)
        return job.job_id if job else "duplicate"

    if fallback_background_tasks is not None:
        fallback_background_tasks.add_task(_drain_one_run_safely, run_id)
        return "inline"

    log.warning("enqueue_skipped", run_id=run_id, reason="no_backend")
    return "skipped"


def _drain_one_run_safely(triggered_by: str) -> None:
    """BackgroundTask wrapper -- never raises into Starlette's task runner."""
    try:
        from app.deps import _SessionLocal, init_engine
        from app.workers.parse_agent_worker import process_one

        init_engine()
        if _SessionLocal is None:
            log.warning("worker_skipped_no_engine", triggered_by=triggered_by)
            return
        with _SessionLocal() as db:
            processed = process_one(db)
        log.info(
            "worker_inline_drain",
            triggered_by=triggered_by,
            processed=processed,
        )
    except Exception as e:  # noqa: BLE001 -- last-line defense
        log.exception("worker_inline_failed", triggered_by=triggered_by, error=str(e))


# ── arq WorkerSettings (entry point for `arq app.queue.WorkerSettings`) ──

async def _arq_process_run(ctx, run_id: str) -> str:
    """arq job: drain a single run."""
    from app.deps import _SessionLocal, init_engine
    from app.workers.parse_agent_worker import process_one

    init_engine()
    if _SessionLocal is None:
        log.warning("arq_skipped_no_engine", run_id=run_id)
        return "skipped"
    with _SessionLocal() as db:
        processed = process_one(db)
    # Notify WS subscribers regardless of which row was processed --
    # we want the dashboard for `run_id` to wake up.
    if processed:
        await publish_run_event(processed, {"event": "completed", "run_id": processed})
    return processed or "no-pending"


async def _on_startup(ctx):
    log.info("arq_worker_started")


async def _on_shutdown(ctx):
    await close_arq_pool()
    await close_pubsub_redis()


class WorkerSettings:
    """Run with: `arq app.queue.WorkerSettings`."""

    functions = [_arq_process_run]
    on_startup = _on_startup
    on_shutdown = _on_shutdown

    @staticmethod
    def redis_settings():
        from arq.connections import RedisSettings
        return RedisSettings.from_dsn(_redis_url())


# arq looks up the function name -- alias so enqueue_job("process_run", ...) works.
_arq_process_run.__name__ = "process_run"  # type: ignore[attr-defined]
