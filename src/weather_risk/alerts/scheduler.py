"""The schedule: an asyncio task inside the FastAPI process (spec 002 FR-201; research.md §1).

Every `poll_seconds` it asks the history store whether a real check is due (none yet, or the last
one started ALERT_INTERVAL_HOURS ago). Because "due" comes from SQLite on the volume, a redeploy
neither skips nor repeats a check. The check itself is blocking (HTTP fetches with pauses), so it
runs in a worker thread and chat keeps answering.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from weather_risk.alerts import service
from weather_risk.alerts.history import History
from weather_risk.settings import Settings, get_settings

log = logging.getLogger("weather_risk.alerts")


async def run_scheduler(settings_factory: Callable[[], Settings] = get_settings,
                        poll_seconds: float = 600,
                        now: Callable[[], datetime] = lambda: datetime.now(UTC),
                        check: Callable | None = None) -> None:
    """Runs until cancelled. Never dies on an error: it logs and tries again next poll."""
    while True:
        try:
            settings = settings_factory()
            if History(settings.alerts_db).is_due(now(), settings.alert_interval_hours):
                summary = await asyncio.to_thread(check or service.run_check, "scheduled")
                log.info("scheduled risk-change check: %s alerts", getattr(summary, "alerts_raised", "?"))
        except service.CheckBusy:
            log.info("scheduled risk-change check skipped: another check is running")
        except Exception as exc:  # class name only: an error text could contain a URL
            log.error("scheduled risk-change check failed: %s", type(exc).__name__)
        await asyncio.sleep(poll_seconds)
