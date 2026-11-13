# Research: Risk-Change Alert

Each decision was confirmed by the user on 2026-11-13. The spec-level choices are in [spec.md](spec.md) under Clarifications; these are the plan-level ones.

## 1. Scheduler: asyncio loop in the FastAPI lifespan

- **Decision:** the FastAPI `lifespan` starts one asyncio task. Every 10 minutes it asks the history store whether a check is due (`now >= last real check start + ALERT_INTERVAL_HOURS`, or no check yet). If one is due, it runs the check with `asyncio.to_thread`, because the fetch is blocking httpx with 3 s pauses. The task is cancelled on shutdown.
- **Rationale:** about 25 lines, no dependency. Because "due" is computed from SQLite, a redeploy neither skips nor repeats a check. A 10-minute poll is ample for a daily job.
- **Off by default:** `ALERT_INTERVAL_HOURS=0` disables it, so local `wra serve` and test clients never fetch live data or move `data/live`, and evals stay on the seed. Railway sets `ALERT_INTERVAL_HOURS=24`.
- **Alternatives:** APScheduler, a dependency whose in-memory schedule restarts from zero on each redeploy unless you add its job store; Railway cron, a second service with no shared process or volume.

## 2. Storage: stdlib sqlite3 with raw SQL

- **Decision:** one file, `DATA_DIR/alerts.sqlite`, with 3 tables (see [data-model.md](data-model.md)), created with `CREATE TABLE IF NOT EXISTS`. A new connection per operation, so it is thread-safe across the scheduler thread and request threads. Each check, with its score records and alerts, is written in one transaction (spec edge case: no half-written history).
- **Rationale:** the constitution names SQLite for score history; 3 small tables do not need an ORM.
- **Alternatives:** SQLModel or SQLAlchemy (a dependency, more to explain); JSON-lines files (needs a constitution justification and hand-written lookups).

## 3. Precision: compare displayed values

- **Decision:** watched scores are rounded to one decimal, as every surface displays them, before they are stored and compared. `change = round(new - old, 1)`, and an alert fires when `abs(change) >= threshold`.
- **Rationale:** an alert's old value, new value and change always match what rankings and chat show. The boundary case (a change of exactly 2.0) is exact after rounding.
- **Alternative:** compare raw floats. A displayed change of 2.0 could then fail to fire, or a displayed 1.9 could fire.

## 4. Delivery: generic JSON webhook, tested with webhook.site

- **Decision:** one POST per alert. The body has a human-readable `text` (Slack-compatible) plus the structured fields ([contracts/webhook.md](contracts/webhook.md)). 5 s timeout and up to 3 attempts with 1 s and 2 s waits. Any non-2xx response or exception counts as a failure, and the status and reason are stored. Every alert is also logged at WARNING with the `text`. The URL is never logged; errors are stored as an exception class name or HTTP status only.
- **Rationale:** webhook.site shows each POST live for the demo, and Slack works unchanged.

## 5. Demo: simulated previous scores

- **Decision:** `simulate_previous(current)` returns a copy of today's real watched scores with two fixed shifts: Dallas `heat` 7.5 lower and Houston `hurricane` 5.0 higher. Detection, recording, delivery and listing then run as normal. The result is exactly 2 alerts: Dallas heat up 7.5, Houston hurricane down 5.0. Overall scores are untouched, which also shows that sub-threshold scores do not alert. The demo check row has `kind='demo'`, its alerts have `is_demo=1`, and no score records are written.
- **Rationale:** it exercises the real code path, cannot affect the next real check, and its output is predictable for a live demo.

## 6. Trigger protection: operator bearer token

- **Decision:** `POST /api/alerts/check` and `/api/alerts/demo` require `Authorization: Bearer <ALERT_ADMIN_TOKEN>`, compared with `hmac.compare_digest`. With no token configured they return 403. They have their own rate limiter (2 per minute, 50 per day). A busy check returns 409. `GET /api/alerts` is public and returns `webhook_configured`, never the URL.
- **Rationale:** the URL is public, and a real check makes 17 calls to free public APIs.

## 7. Refresh reuse

- **Decision:** move the fetch loop from `cli.refresh` to `data/refresh.py` (`fetch_all(root, source) -> RefreshResult` with the failures and per-source results). `wra refresh` keeps its output and exit codes; a check calls the same function on `DATA_DIR` and then `mark_refresh_complete`, so the server's engine reloads (the 001 mechanism).
- **Rationale:** FR-202 says "the same way the refresh command does"; one function guarantees it.

## 8. Concurrency

- **Decision:** a module-level `threading.Lock` in `alerts/service.py`, taken with `acquire(blocking=False)`. If it is busy, the API returns 409 and the scheduler skips that tick.
- **Known limit:** a `wra alerts check` started from a second process at the same moment is not covered by the lock. SQLite transactions keep the history consistent and refresh writes are atomic, but both checks compare with the same last real check, so **the same alerts can be raised and delivered twice**. (Corrected after code review; the first version understated this as "two baseline-equivalent checks".) On Railway there is no second process in practice: the CLI cannot be run on the deployed container from the development machine, and triggers go through the service, which holds the lock.
