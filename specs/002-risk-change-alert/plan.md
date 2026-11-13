# Implementation Plan: Risk-Change Alert

**Branch**: `002-risk-change-alert` (work on `main`) | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-risk-change-alert/spec.md`

## Summary

Add a risk-change check that runs on a schedule inside the existing FastAPI process. A check does the same fetch as `wra refresh` into `DATA_DIR`. It then recomputes scores with the unchanged engine, rounds each hub's overall and five hazard scores to one decimal (as displayed), and compares them with the last recorded real check. Every change of at least 2.0 points becomes an alert.

- **Storage:** checks, score records and alerts go into one SQLite file on the volume (stdlib `sqlite3`, raw SQL).
- **Delivery:** each alert is logged and POSTed to a webhook URL that comes only from env.
- **Viewing:** alerts are listed at public `GET /api/alerts`.
- **Manual trigger:** `wra alerts check|demo|list` from the CLI, or token-protected `POST /api/alerts/check|demo` on the service.
- **Demo:** it compares today's real scores with a simulated previous set (fixed shifts for two hubs), and stores its alerts labeled `demo` without writing score history.
- **Test-first:** change detection is a pure function, developed test-first.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: unchanged (FastAPI, httpx, Typer, Pydantic). New: stdlib `sqlite3`, `asyncio`, `hmac`, `logging` only. No new packages.

**Storage**: SQLite file `DATA_DIR/alerts.sqlite` (Railway volume at `/data`). The JSON snapshot files from 001 are unchanged.

**Testing**: pytest. Test-first for `alerts/detect.py` (detection, rounding, boundary, baseline, new and removed hubs, demo shifts) and for the history queries (last real scores ignore demo checks, persistence across reopen). Smoke tests for the endpoints (auth, 409 busy, list), webhook delivery against a fake transport, CLI commands, and the scheduler's "is a check due" rule.

**Target Platform**: Railway, one container, one instance, volume at `/data`. Local Windows for development.

**Project Type**: web service with a CLI (existing single package).

**Performance Goals**: a demo appears in the list within 1 minute (SC-202). A real check takes about 1 minute, because the Open-Meteo fetch pauses 3 s between hubs, and it runs in a worker thread so chat is never blocked.

**Constraints**:
- The webhook URL never appears in any response, log line, or error message (SC-206).
- Delivery: 5 s timeout, at most 3 attempts.
- Only one check at a time.
- The scheduler is off unless `ALERT_INTERVAL_HOURS > 0`, so local `wra serve` and the evals never fetch live data by surprise.

**Scale/Scope**: 16 hubs × 6 scores = 96 values per check. Score records are kept for the last 30 real checks; the alert list returns the newest 50.

No unknowns remain; the decisions are in [research.md](research.md).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Status |
|---|---|---|
| I. Deterministic scoring, LLM explains | Scores come from the unchanged 001 engine. Detection is a pure function. Old value, new value and change are computed by code. No LLM anywhere in this feature. | Pass |
| II. Enforced structured contracts | No LLM output is consumed. The webhook payload and API responses are Pydantic models. | Pass (n/a for LLM) |
| III. Grounded and honest | Every alert carries the data retrieval dates. Demo alerts are labeled `demo` in the DB, the API, the webhook text and the logs. Known limit (slow drift under the threshold) is in the spec and README. | Pass |
| IV. Test-first and evals | TDD for detection and history queries; smoke tests for routes, CLI and scheduler (the constitution's scope). The eval set is rerun at the end: 20/20 expected, since chat is untouched. | Pass |
| V. Narrow scope, explainable code | No scheduler library and no ORM: an asyncio loop of about 25 lines and about 10 SQL statements. The agent gets no new tools. | Pass |
| VI. Reproducible public data | The check reuses the refresh fetch and its atomic per-source writes. The seed is never modified. Same inputs give the same alerts. | Pass |
| VII. Safe by default | Webhook URL and admin token only from env. Token compared with `hmac.compare_digest`. Trigger endpoints are disabled when no token is set, and rate-limited. The only write is the alert job's own store, which this principle explicitly allows. | Pass |

**Post-design re-check (after Phase 1)**: still passes.
- The data model keeps demo checks out of "last real scores" through a SQL `WHERE kind != 'demo'`, which is covered by a test.
- The contracts never return the webhook URL; `/api/alerts` shows only `webhook_configured: true|false`.

## Project Structure

### Documentation (this feature)

```text
specs/002-risk-change-alert/
├── plan.md              # This file
├── research.md          # Phase 0: scheduler, storage, precision, delivery, demo, auth
├── data-model.md        # Phase 1: tables, detection rule, demo shifts
├── quickstart.md        # Phase 1: run and validation guide
├── contracts/
│   ├── http-api.md      # GET /api/alerts, POST /api/alerts/check, POST /api/alerts/demo
│   ├── cli.md           # wra alerts check | demo | list
│   └── webhook.md       # payload sent to the destination
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/weather_risk/
├── settings.py              # + alert_interval_hours, alert_threshold, alert_webhook_url,
│                            #   alert_admin_token
├── data/
│   └── refresh.py           # NEW: fetch loop moved out of cli.py, shared by refresh and checks
├── alerts/                  # NEW package
│   ├── detect.py            # pure: watched_scores(engine), detect_changes(), simulate_previous()
│   ├── history.py           # sqlite3: schema, last_real_scores, record_check, list_alerts, due
│   ├── notify.py            # webhook payload + POST with timeout/retries; logs every alert
│   ├── service.py           # run_check(kind) / run_demo(): orchestration + one-at-a-time lock
│   └── scheduler.py         # asyncio loop: every 10 min, run a check in a thread if due
├── api/app.py               # + lifespan starts the scheduler; + 3 alert routes
└── cli.py                   # refresh uses data/refresh.py; + `wra alerts check|demo|list`
tests/
├── unit/test_alert_detect.py, test_alert_history.py, test_alert_notify.py
└── smoke/test_api_alerts.py, test_cli_alerts.py, test_scheduler.py
```

**Structure Decision**:
- **Dependencies point downward:** `alerts` depends on `scoring` and `data`; `api` and `cli` depend on `alerts`. Nothing in `scoring` or `agent` imports `alerts`.
- **Chat is unchanged:** the agent cannot reach alerts (FR-218, Principle VII).
- **Refresh is shared:** the fetch loop moves from `cli.py` to `data/refresh.py`, so `wra refresh` and a check fetch data the same way (FR-202).

## Build order (input to /speckit-tasks)

1. Extract `data/refresh.py` from `cli.py`, with behavior unchanged and the existing tests green.
2. `alerts/detect.py`, test-first.
3. `alerts/history.py`, test-first.
4. `alerts/notify.py`: payload and delivery, with a fake transport in tests.
5. `alerts/service.py`: run_check and run_demo, plus the CLI `wra alerts ...`.
6. API routes plus the lifespan scheduler, with smoke tests.
7. Full tests and `wra eval` (20/20 expected), then docs.

## Complexity Tracking

No constitution deviations. One design note: the trigger endpoints add an operator token, the first credential the app checks itself. It is a single shared secret from env, compared in constant time; there are no user accounts, which is in line with the single-tenant demo assumption.
