"""SQLite score history, checks and alerts (spec 002 FR-207..FR-209; data-model.md §3). Test-first."""

from datetime import UTC, datetime, timedelta

import pytest

from weather_risk.alerts.detect import Change
from weather_risk.alerts.history import History

SOURCES = [{"name": "FEMA National Risk Index", "period": "Dec 2025", "retrieved_at": "2026-11-13"}]
T0 = datetime(2026, 11, 13, 18, 0, tzinfo=UTC)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def record(history: History, kind="scheduled", scores=None, changes=(), status="ok", at=T0,
           delivery="not_configured"):
    return history.record_check(
        kind=kind, started_at=_iso(at), finished_at=_iso(at), status=status,
        baseline=not changes and kind != "demo", hubs_checked=len(scores or {}),
        fetch_failures=[], data_retrieved=SOURCES, scores=scores, changes=list(changes),
        delivery_status=delivery)


@pytest.fixture
def history(tmp_path):
    return History(tmp_path / "alerts.sqlite")


def test_schema_is_created_and_starts_empty(history, tmp_path):
    assert (tmp_path / "alerts.sqlite").exists()
    assert history.last_real_scores() == {}
    assert history.last_check() is None
    assert history.list_alerts() == []


def test_last_real_scores_come_from_the_newest_ok_real_check(history):
    record(history, scores={"a": {"overall": 10.0}})
    record(history, kind="manual", scores={"a": {"overall": 20.0}})
    assert history.last_real_scores() == {"a": {"overall": 20.0}}


def test_demo_and_failed_checks_never_become_the_comparison_base(history):
    record(history, scores={"a": {"overall": 10.0}})
    record(history, kind="demo", scores=None,
           changes=[Change(hub_id="a", metric="overall", old=5.0, new=10.0, change=5.0)])
    record(history, status="failed", scores=None)
    assert history.last_real_scores() == {"a": {"overall": 10.0}}


def test_a_check_with_its_alerts_is_recorded_and_listed(history):
    change = Change(hub_id="dallas", metric="heat", old=76.6, new=84.1, change=7.5)
    check_id, alert_ids = record(history, kind="demo", changes=[change], delivery="pending")
    [alert] = history.list_alerts()
    assert alert["id"] == alert_ids[0] and alert["check_id"] == check_id
    assert (alert["hub_id"], alert["metric"], alert["old_value"], alert["new_value"],
            alert["change"]) == ("dallas", "heat", 76.6, 84.1, 7.5)
    assert alert["is_demo"] is True
    assert alert["delivery_status"] == "pending" and alert["delivery_error"] is None
    assert alert["detected_at"] == _iso(T0)
    assert alert["data_retrieved"] == SOURCES
    last = history.last_check()
    assert last["id"] == check_id and last["kind"] == "demo" and last["alerts_raised"] == 1


def test_alerts_are_listed_newest_first_and_limited(history):
    for i in range(3):
        record(history, kind="demo",
               changes=[Change(hub_id=f"h{i}", metric="heat", old=0.0, new=5.0, change=5.0)])
    assert [a["hub_id"] for a in history.list_alerts()] == ["h2", "h1", "h0"]
    assert len(history.list_alerts(limit=2)) == 2


def test_delivery_status_is_updated(history):
    _, [alert_id] = record(history, kind="demo", delivery="pending",
                           changes=[Change(hub_id="a", metric="heat", old=0.0, new=5.0, change=5.0)])
    history.set_delivery(alert_id, "failed", "HTTP 500")
    [alert] = history.list_alerts()
    assert (alert["delivery_status"], alert["delivery_error"]) == ("failed", "HTTP 500")


def test_unknown_delivery_status_is_rejected(history):
    with pytest.raises(ValueError):
        history.set_delivery(1, "sent", None)


def test_score_records_are_kept_for_the_newest_30_real_checks(history):
    for i in range(32):
        record(history, scores={"a": {"overall": float(i)}})
    assert history.score_record_count() == 30
    assert history.last_real_scores() == {"a": {"overall": 31.0}}


def test_history_survives_reopening_the_file(tmp_path):
    first = History(tmp_path / "alerts.sqlite")
    record(first, kind="demo", changes=[Change(hub_id="a", metric="heat", old=0.0, new=5.0, change=5.0)])
    record(first, scores={"a": {"overall": 10.0}})
    reopened = History(tmp_path / "alerts.sqlite")
    assert len(reopened.list_alerts()) == 1
    assert reopened.last_real_scores() == {"a": {"overall": 10.0}}


def test_a_check_is_due_when_none_ran_or_the_interval_has_passed(history):
    assert history.is_due(T0, interval_hours=24) is True
    record(history, scores={"a": {"overall": 10.0}}, at=T0)
    record(history, kind="demo", at=T0 + timedelta(hours=30))  # demos never count
    assert history.is_due(T0 + timedelta(hours=23, minutes=59), interval_hours=24) is False
    assert history.is_due(T0 + timedelta(hours=24), interval_hours=24) is True


def test_alerts_and_unreferenced_checks_are_pruned(history, monkeypatch):
    import weather_risk.alerts.history as module

    monkeypatch.setattr(module, "KEEP_ALERTS", 3)
    monkeypatch.setattr(module, "KEEP_CHECKS", 3)
    for i in range(6):
        record(history, kind="demo",
               changes=[Change(hub_id=f"h{i}", metric="heat", old=0.0, new=5.0, change=5.0)])
    assert [a["hub_id"] for a in history.list_alerts()] == ["h5", "h4", "h3"]
    assert history.check_count() == 3


def test_schema_is_created_once_per_file(tmp_path, monkeypatch):
    import weather_risk.alerts.history as module

    calls = []
    real = module._create_schema
    monkeypatch.setattr(module, "_create_schema", lambda path: (calls.append(path), real(path)))
    History(tmp_path / "a.sqlite")
    History(tmp_path / "a.sqlite")  # e.g. the next GET /api/alerts
    assert len(calls) == 1
