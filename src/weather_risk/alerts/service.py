"""One risk-change check, end to end (spec 002; data-model.md §4).

fetch (real checks only) -> recompute with the unchanged engine -> compare with the last real
check (or, for the demo, a simulated previous set) -> record in one transaction -> log and
deliver each alert. Only one check runs at a time in this process (FR-216).
"""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

from weather_risk.alerts.detect import detect_changes, simulate_previous, watched_scores
from weather_risk.alerts.history import History
from weather_risk.alerts.notify import build_payload, deliver, log_alert
from weather_risk.data.refresh import fetch_all
from weather_risk.scoring.engine import Engine
from weather_risk.settings import Settings, get_settings

log = logging.getLogger("weather_risk.alerts")
_lock = threading.Lock()


class CheckBusy(RuntimeError):
    """Another check is running in this process."""


class CheckSummary(BaseModel):
    check_id: int
    kind: str
    status: str
    baseline: bool
    hubs_checked: int
    alerts_raised: int
    fetch_failures: list[str]
    delivered: int
    delivery_failed: int
    alerts: list[dict]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_check(kind: str = "manual", settings: Settings | None = None, fetch=fetch_all,
              engine_factory: Callable[[], Engine] = Engine.from_settings,
              client: httpx.Client | None = None) -> CheckSummary:
    """A real check: `kind` is "scheduled" or "manual". Fetches live data into DATA_DIR first."""
    if kind not in ("scheduled", "manual"):
        raise ValueError("kind must be 'scheduled' or 'manual'; use run_demo for the demo")
    return _run(kind, settings or get_settings(), fetch, engine_factory, client)


def run_demo(settings: Settings | None = None,
             engine_factory: Callable[[], Engine] = Engine.from_settings,
             client: httpx.Client | None = None) -> CheckSummary:
    """The demo: no fetch, today's real scores against a simulated previous set; never touches
    the real score history (FR-217)."""
    return _run("demo", settings or get_settings(), None, engine_factory, client)


def _run(kind, settings, fetch, engine_factory, client) -> CheckSummary:
    if not _lock.acquire(blocking=False):
        raise CheckBusy("a check is already running")
    try:
        history = History(settings.alerts_db)
        started = _now()
        failures = fetch(settings.data_dir, "all", echo=log.info).failures if fetch else []
        try:
            engine = engine_factory()
            current = watched_scores(engine)
        except Exception as exc:  # recorded as failed; the next check compares with the last good one
            log.error("risk-change check failed while scoring: %s", type(exc).__name__)
            check_id, _ = history.record_check(
                kind=kind, started_at=started, finished_at=_now(), status="failed", baseline=False,
                hubs_checked=0, fetch_failures=failures, data_retrieved=[], scores=None,
                changes=[], delivery_status="not_configured")
            return CheckSummary(check_id=check_id, kind=kind, status="failed", baseline=False,
                                hubs_checked=0, alerts_raised=0, fetch_failures=failures,
                                delivered=0, delivery_failed=0, alerts=[])

        previous = simulate_previous(current) if kind == "demo" else history.last_real_scores()
        baseline = kind != "demo" and not previous
        changes = detect_changes(previous, current, settings.alert_threshold)
        url = settings.alert_webhook_url
        check_id, alert_ids = history.record_check(
            kind=kind, started_at=started, finished_at=_now(), status="ok", baseline=baseline,
            hubs_checked=len(current), fetch_failures=failures,
            data_retrieved=engine.data_sources(), scores=current, changes=changes,
            delivery_status="pending" if url else "not_configured")

        delivered = failed = 0
        for alert in _alerts_by_id(history, alert_ids):
            payload = build_payload(alert, settings.alert_threshold, engine.hubs[alert["hub_id"]].name)
            log_alert(payload)
            if url:
                status, error = deliver(url.get_secret_value(), payload, client)
                history.set_delivery(alert["id"], status, error)
                delivered += status == "delivered"
                failed += status == "failed"

        return CheckSummary(
            check_id=check_id, kind=kind, status="ok", baseline=baseline,
            hubs_checked=len(current), alerts_raised=len(changes), fetch_failures=failures,
            delivered=delivered, delivery_failed=failed,
            alerts=[_with_name(a, engine) for a in _alerts_by_id(history, alert_ids)])
    finally:
        _lock.release()


def _alerts_by_id(history: History, ids: list[int]) -> list[dict]:
    """The just-recorded alerts, oldest first, as stored."""
    wanted = set(ids)
    rows = history.list_alerts(limit=max(len(ids), 1)) if ids else []
    return sorted((a for a in rows if a["id"] in wanted), key=lambda a: a["id"])


def _with_name(alert: dict, engine: Engine) -> dict:
    hub = engine.hubs.get(alert["hub_id"])
    return {**alert, "hub_name": hub.name if hub else alert["hub_id"]}
