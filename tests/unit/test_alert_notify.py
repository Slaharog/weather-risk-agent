"""Webhook payload and delivery (spec 002 FR-210..FR-213, SC-206; contracts/webhook.md). Test-first."""

import logging

import httpx
import pytest

from weather_risk.alerts.notify import build_payload, deliver, log_alert

URL = "https://hooks.example.test/secret-path-123"
SOURCES = [{"name": "FEMA National Risk Index", "period": "December 2025 release",
            "retrieved_at": "2026-11-13"}]


def alert(**overrides):
    base = {"id": 3, "check_id": 6, "hub_id": "dallas", "metric": "heat", "old_value": 76.6,
            "new_value": 84.1, "change": 7.5, "detected_at": "2026-11-13T17:40:00Z",
            "is_demo": True, "data_retrieved": SOURCES, "delivery_status": "pending",
            "delivery_error": None}
    return {**base, **overrides}


def test_demo_payload_text_is_prefixed_and_uses_the_stored_numbers():
    payload = build_payload(alert(), threshold=2.0, hub_name="Dallas")
    assert payload["text"] == (
        "[DEMO] Dallas heat score rose 7.5 points: 76.6 -> 84.1 (threshold 2.0). "
        "Data: FEMA National Risk Index, December 2025 release (retrieved 2026-11-13).")
    assert payload["alert"] == {
        "id": 3, "hub_id": "dallas", "hub_name": "Dallas", "metric": "heat", "old_value": 76.6,
        "new_value": 84.1, "change": 7.5, "threshold": 2.0, "detected_at": "2026-11-13T17:40:00Z",
        "is_demo": True, "data_retrieved": SOURCES}


def test_real_alert_has_no_prefix_and_says_fell_for_a_decrease():
    payload = build_payload(alert(is_demo=False, old_value=65.1, new_value=60.1, change=-5.0,
                                  metric="hurricane", hub_id="houston"),
                            threshold=2.0, hub_name="Houston")
    assert payload["text"].startswith("Houston hurricane score fell 5.0 points: 65.1 -> 60.1")


def client_returning(*statuses):
    calls = iter(statuses)

    def handler(request):
        status = next(calls)
        if isinstance(status, Exception):
            raise status
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler))


def no_wait(seconds):
    pass


def test_delivered_on_first_success():
    assert deliver(URL, {"text": "x"}, client_returning(200), wait=no_wait) == ("delivered", None)


def test_retries_until_success_within_three_attempts():
    assert deliver(URL, {"text": "x"}, client_returning(500, 500, 204), wait=no_wait) == (
        "delivered", None)


def test_three_failures_give_failed_with_the_last_status():
    assert deliver(URL, {"text": "x"}, client_returning(500, 502, 500), wait=no_wait) == (
        "failed", "HTTP 500")


def test_exception_is_reported_by_class_name_only():
    timeout = httpx.ConnectTimeout(f"timed out connecting to {URL}")
    status, error = deliver(URL, {"text": "x"}, client_returning(timeout, timeout, timeout),
                            wait=no_wait)
    assert (status, error) == ("failed", "ConnectTimeout")


def test_waits_one_then_two_seconds_between_attempts():
    waits = []
    deliver(URL, {"text": "x"}, client_returning(500, 500, 500), wait=waits.append)
    assert waits == [1, 2]


@pytest.mark.parametrize("statuses", [(200,), (500, 500, 500)])
def test_the_url_never_reaches_the_logs(caplog, statuses):
    caplog.set_level(logging.DEBUG)  # even at DEBUG, nothing may print the URL (SC-206)
    deliver(URL, {"text": "x"}, client_returning(*statuses), wait=no_wait)
    log_alert({"text": "Dallas heat score rose 7.5 points"})
    assert "secret-path-123" not in caplog.text
    assert "Dallas heat score rose" in caplog.text
