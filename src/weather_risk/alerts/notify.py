"""Alert delivery: one JSON POST per alert to a webhook from configuration only (spec 002,
FR-210..FR-213; contracts/webhook.md). Every alert is also logged. The URL is a secret: it is
never logged, returned, or put into an error message (SC-206).
"""

import logging
import ssl
import time
from collections.abc import Callable

import httpx

log = logging.getLogger("weather_risk.alerts")

# httpx logs every request as "HTTP Request: POST <full URL>" at INFO, which would leak the
# webhook URL whenever the app runs at INFO level. Keep httpx and httpcore at WARNING.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

TIMEOUT_SECONDS = 5
ATTEMPTS = 3


def build_payload(alert: dict, threshold: float, hub_name: str) -> dict:
    """Human-readable `text` (Slack-compatible) plus the structured fields. Every number comes
    from the stored alert row."""
    direction = "rose" if alert["change"] > 0 else "fell"
    sources = "; ".join(f"{s['name']}, {s['period']} (retrieved {s['retrieved_at']})"
                        for s in alert["data_retrieved"])
    text = (f"{'[DEMO] ' if alert['is_demo'] else ''}{hub_name} {alert['metric']} score "
            f"{direction} {abs(alert['change']):.1f} points: {alert['old_value']:.1f} -> "
            f"{alert['new_value']:.1f} (threshold {threshold:.1f}). Data: {sources}.")
    fields = ("id", "hub_id", "metric", "old_value", "new_value", "change", "detected_at",
              "is_demo", "data_retrieved")
    body = {k: alert[k] for k in fields}
    return {"text": text, "alert": {**body, "hub_name": hub_name, "threshold": threshold}}


def deliver(url: str, payload: dict, client: httpx.Client | None = None,
            wait: Callable[[float], None] = time.sleep) -> tuple[str, str | None]:
    """POST with a short timeout and up to 3 attempts (waits of 1 s, then 2 s).
    Returns ("delivered", None) or ("failed", reason), where the reason is an HTTP status or an
    exception class name, never text that could contain the URL."""
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=TIMEOUT_SECONDS, verify=ssl.create_default_context())
    error = None
    try:
        for attempt in range(ATTEMPTS):
            if attempt:
                wait(attempt)  # 1 s, then 2 s
            try:
                response = client.post(url, json=payload)
                if response.is_success:
                    return "delivered", None
                error = f"HTTP {response.status_code}"
            except Exception as exc:  # network errors, timeouts, bad URL
                error = type(exc).__name__
        return "failed", error
    finally:
        if own_client:
            client.close()


def log_alert(payload: dict) -> None:
    """Every alert goes to the service log, configured destination or not (FR-212)."""
    log.warning("risk-change alert: %s", payload["text"])
