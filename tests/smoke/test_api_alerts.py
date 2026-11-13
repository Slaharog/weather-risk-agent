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
