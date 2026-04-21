"""Pure-unit test for app.queue inline-backend path (no Redis, no arq)."""

from __future__ import annotations

import pytest

from app.queue import _backend, enqueue_parse_run, publish_run_event, subscribe_run_events


@pytest.fixture(autouse=True)
def _force_inline(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("DASHBOARD_QUEUE_BACKEND", "inline")
    yield


def test_backend_is_inline():
    assert _backend() == "inline"


@pytest.mark.asyncio
async def test_publish_event_is_noop_inline():
    # Should not raise even though no Redis is configured.
    await publish_run_event("run-x", {"event": "test"})


@pytest.mark.asyncio
async def test_subscribe_yields_empty_queue_inline():
    async with subscribe_run_events("run-x") as q:
        assert q.empty()


@pytest.mark.asyncio
async def test_enqueue_with_no_background_tasks_returns_skipped():
    result = await enqueue_parse_run("run-x", fallback_background_tasks=None)
    assert result == "skipped"


@pytest.mark.asyncio
async def test_enqueue_dispatches_to_background_tasks():
    class _BG:
        def __init__(self):
            self.tasks = []

        def add_task(self, fn, *args, **kwargs):
            self.tasks.append((fn, args, kwargs))

    bg = _BG()
    result = await enqueue_parse_run("run-y", fallback_background_tasks=bg)
    assert result == "inline"
    assert len(bg.tasks) == 1
    fn, args, _ = bg.tasks[0]
    assert args == ("run-y",)
    assert fn.__name__ == "_drain_one_run_safely"
