"""Alert HTTP API (spec 002, contracts/http-api.md)."""

import pytest
from fastapi.testclient import TestClient

from weather_risk.alerts.detect import Change
from weather_risk.alerts.history import History
from weather_risk.api import app as app_module
from weather_risk.settings import get_settings

client = TestClient(app_module.app)
SECRET_URL = "https://hooks.example.test/very-secret-path"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def add_demo_alerts(n):
    history = History(get_settings().alerts_db)
    for i in range(n):
        history.record_check(
            kind="demo", started_at=f"2026-11-13T18:0{i}:00Z", finished_at=f"2026-11-13T18:0{i}:00Z",
            status="ok", baseline=False, hubs_checked=16, fetch_failures=[], data_retrieved=[],
            scores=None, changes=[Change(hub_id="dallas", metric="heat", old=76.6, new=84.1, change=7.5)],
            delivery_status="delivered")


def test_empty_list_before_any_check(data_dir):
    body = client.get("/api/alerts").json()
    assert body["alerts"] == [] and body["last_check"] is None
    assert body["threshold"] == 2.0 and body["webhook_configured"] is False


def test_alerts_are_listed_newest_first_with_hub_names(data_dir):
    add_demo_alerts(2)
    body = client.get("/api/alerts").json()
    assert [a["id"] for a in body["alerts"]] == [2, 1]
    first = body["alerts"][0]
    assert first["hub_name"] == "Dallas, TX" and first["is_demo"] is True
    assert body["last_check"]["kind"] == "demo"
    assert len(client.get("/api/alerts?limit=1").json()["alerts"]) == 1


def test_the_webhook_url_is_never_returned(data_dir, monkeypatch):
    monkeypatch.setenv("ALERT_WEBHOOK_URL", SECRET_URL)
    add_demo_alerts(1)
    response = client.get("/api/alerts")
    assert response.json()["webhook_configured"] is True
    assert "very-secret-path" not in response.text


@pytest.mark.parametrize("limit", [0, 51])
def test_limit_is_validated(data_dir, limit):
    assert client.get(f"/api/alerts?limit={limit}").status_code == 422


def test_alerts_page_is_served_and_linked_from_the_chat_header():
    page = client.get("/alerts")
    assert page.status_code == 200 and "Recent alerts" in page.text
    assert "innerHTML" not in page.text  # values are rendered with textContent only
    assert 'href="/alerts"' in client.get("/").text


# ---------- POST /api/alerts/check (T217) ----------

TOKEN = "test-operator-token-0123456789abcdef"  # >= 32 characters


@pytest.fixture
def trigger(data_dir, monkeypatch):
    from weather_risk.alerts import service
    from weather_risk.api.limits import RateLimiter
    from weather_risk.data.refresh import RefreshResult

    monkeypatch.setattr(service, "fetch_all", lambda root, source, echo: RefreshResult())
    monkeypatch.setattr(app_module, "trigger_limiter", RateLimiter(per_minute=2, per_day=50))
    monkeypatch.setenv("ALERT_ADMIN_TOKEN", TOKEN)


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_check_is_refused_when_no_token_is_configured(trigger, monkeypatch):
    monkeypatch.setenv("ALERT_ADMIN_TOKEN", "")
    assert client.post("/api/alerts/check", headers=auth()).status_code == 403


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}])
def test_check_is_refused_without_the_right_token(trigger, headers):
    assert client.post("/api/alerts/check", headers=headers).status_code == 403


def test_check_with_the_token_runs_and_returns_a_summary(trigger):
    response = client.post("/api/alerts/check", headers=auth())
    assert response.status_code == 200
    body = response.json()
    assert (body["kind"], body["status"], body["baseline"], body["hubs_checked"]) == (
        "manual", "ok", True, 16)


def test_check_while_another_runs_gives_409(trigger):
    from weather_risk.alerts import service

    with service._lock:
        assert client.post("/api/alerts/check", headers=auth()).status_code == 409


def test_third_trigger_within_a_minute_gives_429(trigger):
    codes = [client.post("/api/alerts/check", headers=auth()).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---------- POST /api/alerts/demo (T218) ----------

def test_demo_needs_the_token(trigger):
    assert client.post("/api/alerts/demo").status_code == 403


def test_demo_gives_two_labeled_alerts_and_changes_nothing_real(trigger):
    rankings_before = client.get("/api/rankings").content
    body = client.post("/api/alerts/demo", headers=auth()).json()
    assert body["kind"] == "demo" and body["alerts_raised"] == 2
    assert [(a["hub_id"], a["metric"], a["change"], a["is_demo"]) for a in body["alerts"]] == [
        ("dallas", "heat", 7.5, True), ("houston", "hurricane", -5.0, True)]
    assert client.get("/api/rankings").content == rankings_before  # byte-identical (FR-218)

    real = client.post("/api/alerts/check", headers=auth()).json()  # unchanged data
    assert real["baseline"] is True and real["alerts_raised"] == 0  # the demo left no history


# ---------- security review fixes (T221) ----------

def test_repeated_wrong_tokens_are_throttled(trigger, monkeypatch):
    from weather_risk.api.limits import RateLimiter

    monkeypatch.setattr(app_module, "auth_failure_limiter", RateLimiter(per_minute=5, per_day=500))
    codes = [client.post("/api/alerts/demo", headers=auth("wrong")).status_code for _ in range(6)]
    assert codes == [403] * 5 + [429]


def test_alert_list_works_when_the_engine_cannot_load(data_dir, monkeypatch):
    add_demo_alerts(1)

    def broken():
        raise FileNotFoundError("snapshot missing")

    monkeypatch.setattr(app_module.engines, "get", broken)
    response = client.get("/api/alerts")
    assert response.status_code == 200 and response.json()["alerts"][0]["hub_name"] == "Dallas, TX"
