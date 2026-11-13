"""The in-process schedule (spec 002 FR-201): runs a check only when one is due."""

import asyncio
from datetime import UTC, datetime

from weather_risk.alerts.history import History
from weather_risk.alerts.scheduler import run_scheduler
from weather_risk.settings import Settings

NOW = datetime(2026, 11, 13, 18, 0, tzinfo=UTC)


def run_briefly(settings, calls):
    async def go():
        try:
            await asyncio.wait_for(
                run_scheduler(lambda: settings, poll_seconds=0.01, now=lambda: NOW,
                              check=lambda kind: calls.append(kind)), timeout=0.1)
        except TimeoutError:
            pass
    asyncio.run(go())


def test_runs_a_scheduled_check_when_none_has_run(tmp_path):
    calls = []
    run_briefly(Settings(data_dir=tmp_path, alert_interval_hours=24), calls)
    assert calls and set(calls) == {"scheduled"}


def test_does_not_run_when_the_last_check_is_recent(tmp_path):
    settings = Settings(data_dir=tmp_path, alert_interval_hours=24)
    History(settings.alerts_db).record_check(
        kind="scheduled", started_at="2026-11-13T17:00:00Z", finished_at="2026-11-13T17:01:00Z",
        status="ok", baseline=True, hubs_checked=1, fetch_failures=[], data_retrieved=[],
        scores={"a": {"overall": 1.0}}, changes=[], delivery_status="not_configured")
    calls = []
    run_briefly(settings, calls)
    assert calls == []


def test_an_error_in_a_check_does_not_stop_the_loop(tmp_path):
    calls = []

    def failing(kind):
        calls.append(kind)
        raise RuntimeError("boom")

    async def go():
        try:
            await asyncio.wait_for(run_scheduler(
                lambda: Settings(data_dir=tmp_path, alert_interval_hours=24), poll_seconds=0.01,
                now=lambda: NOW, check=failing), timeout=0.1)
        except TimeoutError:
            pass
    asyncio.run(go())
    assert len(calls) >= 2  # it kept polling after the first failure


def test_app_lifespan_starts_no_scheduler_by_default():
    from fastapi.testclient import TestClient

    from weather_risk.api import app as app_module

    with TestClient(app_module.app) as client:  # runs the lifespan
        assert client.get("/api/health").status_code == 200
