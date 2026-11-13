"""The whole check path with a fake fetch and a fake webhook (spec 002 US1, SC-204). No network."""

import httpx
import pytest

from weather_risk.alerts import service
from weather_risk.alerts.history import History
from weather_risk.data.refresh import RefreshResult
from weather_risk.scoring.engine import Engine
from weather_risk.settings import Settings


def no_fetch(root, source, echo):
    return RefreshResult()  # writes nothing: the seed stays the data


@pytest.fixture
def make_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))  # the engine reads the seed (empty live dir)

    def make(**kw):
        return Settings(data_dir=tmp_path, **kw)
    return make


def shifted(hub_id, metric, delta):
    """An engine factory whose score for one hub and metric is moved by `delta` points."""
    def factory():
        engine = Engine.from_settings()
        original = engine.metric_score
        engine.metric_score = lambda h, m: original(h, m) + (delta if (h, m) == (hub_id, metric) else 0)
        return engine
    return factory


def webhook(*statuses):
    calls = iter(statuses)
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(next(calls))))


def test_first_check_is_a_baseline_with_no_alerts(make_settings):
    summary = service.run_check("manual", make_settings(), fetch=no_fetch)
    assert (summary.status, summary.baseline, summary.hubs_checked, summary.alerts_raised) == (
        "ok", True, 16, 0)


def test_a_shift_past_the_threshold_is_recorded_and_delivered(make_settings):
    settings = make_settings(alert_webhook_url="https://hooks.example.test/x")
    service.run_check("scheduled", settings, fetch=no_fetch)
    summary = service.run_check("scheduled", settings, fetch=no_fetch,
                                engine_factory=shifted("chicago", "winter", 3.0),
                                client=webhook(200))
    assert summary.baseline is False and summary.alerts_raised == 1 and summary.delivered == 1
    [alert] = summary.alerts
    assert (alert["hub_id"], alert["hub_name"], alert["metric"], alert["is_demo"]) == (
        "chicago", "Chicago, IL", "winter", False)
    assert alert["change"] == pytest.approx(3.0, abs=0.1)  # rounding of both sides
    assert alert["delivery_status"] == "delivered"


def test_without_a_webhook_alerts_are_recorded_as_not_configured(make_settings):
    settings = make_settings()
    service.run_check("manual", settings, fetch=no_fetch)
    summary = service.run_check("manual", settings, fetch=no_fetch,
                                engine_factory=shifted("miami", "flood", -4.0))
    assert summary.alerts[0]["delivery_status"] == "not_configured"
    assert summary.delivered == summary.delivery_failed == 0


def test_an_unreachable_webhook_still_completes_the_check(make_settings, monkeypatch):
    monkeypatch.setattr("weather_risk.alerts.notify.time.sleep", lambda s: None)
    settings = make_settings(alert_webhook_url="https://hooks.example.test/x")
    service.run_check("manual", settings, fetch=no_fetch)
    summary = service.run_check("manual", settings, fetch=no_fetch,
                                engine_factory=shifted("denver", "heat", 5.0),
                                client=webhook(500, 500, 500))
    assert summary.status == "ok" and summary.delivery_failed == 1
    stored = History(settings.alerts_db).list_alerts()[0]
    assert (stored["delivery_status"], stored["delivery_error"]) == ("failed", "HTTP 500")


def test_fetch_failures_are_recorded_but_raise_no_alert(make_settings):
    settings = make_settings()
    service.run_check("manual", settings, fetch=no_fetch)
    summary = service.run_check("manual", settings,
                                fetch=lambda root, source, echo: RefreshResult(failures=["nri"]))
    assert summary.fetch_failures == ["nri"] and summary.alerts_raised == 0


def test_a_scoring_failure_is_recorded_as_failed(make_settings):
    def broken():
        raise FileNotFoundError("snapshot missing")
    summary = service.run_check("manual", make_settings(), fetch=no_fetch, engine_factory=broken)
    assert summary.status == "failed"


def test_only_one_check_runs_at_a_time(make_settings):
    with service._lock:
        with pytest.raises(service.CheckBusy):
            service.run_check("manual", make_settings(), fetch=no_fetch)
