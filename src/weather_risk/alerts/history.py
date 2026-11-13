"""Score history, checks and alerts in one SQLite file on the volume (spec 002; data-model.md §3).

Stdlib sqlite3 with raw SQL, no ORM. A new connection per operation, so the scheduler thread and
request threads never share one. A check, its score records and its alerts are written in one
transaction, so a crash never leaves half a check behind.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from weather_risk.alerts.detect import Change, Scores

KEEP_REAL_CHECKS = 30
DELIVERY_STATUSES = ("pending", "delivered", "failed", "not_configured")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('scheduled', 'manual', 'demo')),
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed')),
    baseline INTEGER NOT NULL,
    hubs_checked INTEGER NOT NULL,
    alerts_raised INTEGER NOT NULL,
    fetch_failures TEXT NOT NULL,
    data_retrieved TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS score_records (
    check_id INTEGER NOT NULL REFERENCES checks(id),
    hub_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    PRIMARY KEY (check_id, hub_id, metric)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id INTEGER NOT NULL REFERENCES checks(id),
    hub_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    old_value REAL NOT NULL,
    new_value REAL NOT NULL,
    change REAL NOT NULL,
    detected_at TEXT NOT NULL,
    is_demo INTEGER NOT NULL,
    data_retrieved TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    delivery_error TEXT
);
"""

# The comparison base: the newest successful check that was not a demo.
LAST_REAL_OK = "SELECT MAX(id) FROM checks WHERE kind != 'demo' AND status = 'ok'"


class History:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """One connection per operation; commits on success, rolls back on error, always closes."""
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:  # transaction
                yield db
        finally:
            db.close()

    def record_check(self, *, kind: str, started_at: str, finished_at: str, status: str,
                     baseline: bool, hubs_checked: int, fetch_failures: list[str],
                     data_retrieved: list[dict], scores: Scores | None, changes: list[Change],
                     delivery_status: str) -> tuple[int, list[int]]:
        """Insert one check with its score records (real checks only) and alerts. Returns the
        check id and the new alert ids."""
        _check_status(delivery_status)
        sources = json.dumps(data_retrieved)
        with self._connect() as db:
            check_id = db.execute(
                "INSERT INTO checks (kind, started_at, finished_at, status, baseline, hubs_checked,"
                " alerts_raised, fetch_failures, data_retrieved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, started_at, finished_at, status, int(baseline), hubs_checked, len(changes),
                 json.dumps(fetch_failures), sources)).lastrowid
            if scores and kind != "demo":
                db.executemany(
                    "INSERT INTO score_records (check_id, hub_id, metric, value) VALUES (?, ?, ?, ?)",
                    [(check_id, hub, metric, value)
                     for hub, metrics in scores.items() for metric, value in metrics.items()])
                db.execute(  # retention: score records of the newest KEEP_REAL_CHECKS real checks
                    "DELETE FROM score_records WHERE check_id NOT IN (SELECT id FROM checks"
                    " WHERE kind != 'demo' ORDER BY id DESC LIMIT ?)", (KEEP_REAL_CHECKS,))
            alert_ids = [db.execute(
                "INSERT INTO alerts (check_id, hub_id, metric, old_value, new_value, change,"
                " detected_at, is_demo, data_retrieved, delivery_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (check_id, c.hub_id, c.metric, c.old, c.new, c.change, started_at,
                 int(kind == "demo"), sources, delivery_status)).lastrowid for c in changes]
        return check_id, alert_ids

    def last_real_scores(self) -> Scores:
        with self._connect() as db:
            rows = db.execute(f"SELECT hub_id, metric, value FROM score_records"
                              f" WHERE check_id = ({LAST_REAL_OK})").fetchall()
        scores: Scores = {}
        for row in rows:
            scores.setdefault(row["hub_id"], {})[row["metric"]] = row["value"]
        return scores

    def set_delivery(self, alert_id: int, status: str, error: str | None) -> None:
        _check_status(status)
        with self._connect() as db:
            db.execute("UPDATE alerts SET delivery_status = ?, delivery_error = ? WHERE id = ?",
                       (status, error, alert_id))

    def list_alerts(self, limit: int = 50) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{**dict(r), "is_demo": bool(r["is_demo"]),
                 "data_retrieved": json.loads(r["data_retrieved"])} for r in rows]

    def last_check(self) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM checks ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return {**dict(row), "baseline": bool(row["baseline"]),
                "fetch_failures": json.loads(row["fetch_failures"]),
                "data_retrieved": json.loads(row["data_retrieved"])}

    def is_due(self, now: datetime, interval_hours: float) -> bool:
        """True if no real check ever ran, or the newest one started `interval_hours` ago or more.
        Failed real checks count too, so a failing source is not retried every poll."""
        with self._connect() as db:
            row = db.execute("SELECT started_at FROM checks WHERE kind != 'demo'"
                             " ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return True
        last = datetime.strptime(row["started_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=now.tzinfo)
        return now >= last + timedelta(hours=interval_hours)

    def score_record_count(self) -> int:
        with self._connect() as db:
            return db.execute("SELECT COUNT(*) FROM score_records").fetchone()[0]


def _check_status(status: str) -> None:
    if status not in DELIVERY_STATUSES:
        raise ValueError(f"delivery status must be one of {DELIVERY_STATUSES}")
