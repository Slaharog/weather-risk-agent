---

description: "Task list for feature 002: Risk-Change Alert"
---

# Tasks: Risk-Change Alert

**Input**: Design documents from `/specs/002-risk-change-alert/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Constitution Principle IV: test-first for detection and history logic (each TDD test task is written and seen failing before its implementation task); smoke tests for routes, CLI, page, and scheduler.

**Task IDs** start at T201 (matching FR-2xx) so commit messages do not collide with feature 001's T001-T062.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 detect and deliver, US2 see alerts, US3 trigger on demand, US4 demonstrate (spec.md)
- Commit after every task, with the Co-Authored-By line.

## Path Conventions

Single project: `src/weather_risk/`, `tests/`, `scripts/` at the repository root (plan.md, Project Structure).

---

## Phase 1: Setup

- [X] T201 Add alert settings to `src/weather_risk/settings.py`: `alert_interval_hours: float = 0` (0 = scheduler off), `alert_threshold: float = 2.0` (must be > 0), `alert_webhook_url: SecretStr | None = None`, `alert_admin_token: SecretStr | None = None`, and a property `alerts_db -> data_dir / "alerts.sqlite"`. List them, with no real values, in `.env.example`. Run the full test suite: still green.
- [X] T202 [P] Create the empty package `src/weather_risk/alerts/__init__.py`.

---

## Phase 2: Foundational (blocks every story)

- [X] T203 Move the fetch loop out of `cli.refresh` into `src/weather_risk/data/refresh.py`: `fetch_all(root: Path, source: str = "all", echo=print) -> RefreshResult` (fields `failures: list[str]` such as `"weather:dallas"` or `"nri"`). It keeps the 3 s pause between hubs, the per-source atomic save, and the `mark_refresh_complete` at the end. `cli.refresh` calls it and keeps its exact output and exit codes. Existing tests stay green, and `wra refresh --help` is unchanged.
- [X] T204 [P] TDD: write `tests/unit/test_alert_detect.py` (failing first), covering:
  - `watched_scores(engine)` returns 16 hubs × 6 metrics (`overall, winter, hurricane, flood, heat, severe_storms`), each `round(metric_score, 1)`.
  - `detect_changes(previous, current, threshold)`:
    - a change of exactly 2.0 alerts, and 1.9 does not;
    - the change is `round(new - old, 1)` with its sign (increase or decrease);
    - an empty `previous` gives `[]`;
    - a hub only in `current` and a hub only in `previous` give no change;
    - the output is sorted by `(hub_id, metric)`;
    - `threshold <= 0` raises `ValueError`.
  - `simulate_previous(current)`: `dallas.heat - 7.5` and `houston.hurricane + 5.0`, "rounded to 1 decimal, clamped to 0-100"; a missing hub is skipped; the input is not mutated; with the default threshold it gives exactly 2 changes.
- [X] T205 Implement `src/weather_risk/alerts/detect.py` (`Change` model, `watched_scores`, `detect_changes`, `simulate_previous`, `DEMO_SHIFTS`) until T204 passes.
- [X] T206 [P] TDD: write `tests/unit/test_alert_history.py` (failing first), using `tmp_path` and covering:
  - the schema is created on first open;
  - `last_real_scores()` is `{}` with no checks;
  - `record_check(...)` writes the check, its score records and its alerts in one transaction;
  - `last_real_scores()` returns the newest `kind != 'demo' AND status = 'ok'` check, ignoring a newer demo check and a newer failed check;
  - demo checks store no score records;
  - `list_alerts(limit)` returns newest first, with `is_demo` as a bool;
  - `last_check()` returns the newest check of any kind;
  - `set_delivery(alert_id, status, error)` works, with status in "`pending` (only while sending), `delivered`, `failed`, or `not_configured`";
  - retention keeps score records of the newest 30 real checks only;
  - data survives closing and reopening the file (SC-203);
  - `is_due(now, interval_hours)` is True with no real check, and False until `last real started_at + interval`.
- [X] T207 Implement `src/weather_risk/alerts/history.py` with stdlib `sqlite3` and raw SQL, using the tables from data-model.md §3 (`checks`, `score_records`, `alerts`), `CREATE TABLE IF NOT EXISTS`, and a new connection per operation. Make T206 pass.

**Checkpoint**: detection and history are proven by tests. Nothing is wired yet, and the app is unchanged.

---

## Phase 3: User Story 1 - Get alerted when a hub's score changes (P1) 🎯 MVP

**Goal**: a check fetches, recomputes, detects, records, logs and delivers.

**Independent Test**: with a recorded previous check and changed data, one check records and delivers exactly the expected alerts (fake transport).

- [X] T208 [P] [US1] TDD: write `tests/unit/test_alert_notify.py` (failing first), covering:
  - `build_payload(alert, threshold)` gives a `text` that starts with `[DEMO] ` only for demo alerts, says "rose" or "fell", and contains old, new and change exactly as stored, plus the data retrieval dates; the `alert` object has the fields from contracts/webhook.md.
  - `deliver(url, payload, client)` with an `httpx.MockTransport`: a 200 gives `delivered`; 500, 500, 200 gives `delivered` after 3 attempts; three 500s give `failed` / `HTTP 500`; a timeout gives `failed` / `ConnectTimeout`-style class name. The URL never appears in the returned error, and (with `caplog`) never in any log line from `deliver` or `log_alert` (SC-206).
- [ ] T209 [US1] Implement `src/weather_risk/alerts/notify.py`: `build_payload`, and `deliver` with a 5 s timeout, at most 3 attempts and 1 s / 2 s waits (the wait function is injectable so tests don't sleep). Also `log_alert(alert)`, which logs the `text` at WARNING and never the URL. Make T208 pass.
- [ ] T210 [US1] Implement `src/weather_risk/alerts/service.py`:
  - a module `threading.Lock`;
  - `run_check(kind, settings, fetch=fetch_all) -> CheckSummary`, following the lifecycle in data-model.md §4. If the lock is busy it raises `CheckBusy`. The fetch is injectable for tests. A scoring failure records the check as `failed` with no score records.
  - `CheckSummary` (a Pydantic model) as in contracts/http-api.md.
- [ ] T211 [US1] Write `tests/smoke/test_alert_service.py`, using a fake fetch that writes nothing and a MockTransport webhook:
  - the first check is a baseline with 0 alerts;
  - a second check with a monkeypatched engine score shift of +3.0 on one hub gives exactly the expected alert, recorded and delivered;
  - no webhook configured gives `not_configured`;
  - an unreachable webhook still completes the check, with `failed` recorded (SC-204);
  - a concurrent call raises `CheckBusy`.
- [ ] T212 [US1] Add `wra alerts check` and `wra alerts list [--limit N]` to `src/weather_risk/cli.py` (a Typer sub-app), with output and exit codes as in contracts/cli.md. Add a smoke test in `tests/smoke/test_cli_alerts.py` with the fake fetch.
- [ ] T213 [US1] Implement `src/weather_risk/alerts/scheduler.py`: `async def run_scheduler(settings, poll_seconds=600)`, which loops forever. On each tick, if `is_due(...)` is true, it runs `await asyncio.to_thread(run_check, "scheduled", ...)`. It catches and logs `CheckBusy` and any exception, so the loop never dies. Wire it into a FastAPI `lifespan` in `src/weather_risk/api/app.py`, started only when `alert_interval_hours > 0` and cancelled on shutdown. Add a smoke test in `tests/smoke/test_scheduler.py` (a short poll, a monkeypatched `run_check`, and a check that it runs once when due and not when not due).

**Checkpoint**: `wra alerts check` works locally; the first run is a baseline.

---

## Phase 4: User Story 2 - See recent alerts and checks (P1)

**Independent Test**: after recording alerts, `GET /api/alerts` and `/alerts` show them newest first, with the demo label.

- [ ] T214 [US2] Add `GET /api/alerts?limit=` (1 to 50, default 50) in `src/weather_risk/api/app.py`, returning `threshold`, `interval_hours`, `webhook_configured` (a bool only, never the URL), `last_check` and `alerts` with `hub_name`, per contracts/http-api.md. Add a smoke test in `tests/smoke/test_api_alerts.py`, including that the configured URL string appears nowhere in the response body (SC-206).
- [ ] T215 [US2] Create `src/weather_risk/api/static/alerts.html`:
  - It reuses the chat page's color tokens (light and dark).
  - On load and on a "Reload" button, it fetches `/api/alerts` and renders the summary of the last check, the threshold, whether a destination is configured, and a table with one row per alert (hub, score, old → new, change, time, a "demo" text badge, delivery status).
  - It uses `textContent` only, has an empty state, and shows an error state if the fetch fails.
  - It has no trigger controls.
  - Add `GET /alerts` (FileResponse), and one "Alerts" link in the header of `src/weather_risk/api/static/index.html` (no other change). Smoke test: `/alerts` returns 200 and contains "Recent alerts"; `/` contains `href="/alerts"`.
- [ ] T216 [US2] Run the impeccable audit on `alerts.html` and the changed header (keyboard focus, contrast in both modes, the demo label not conveyed by color alone). Fix the material findings, and record the triage in the task's commit message.

---

## Phase 5: User Story 3 - Trigger a check on demand (P2)

- [ ] T217 [US3] Add `POST /api/alerts/check` in `src/weather_risk/api/app.py`:
  - a bearer token compared with `hmac.compare_digest`;
  - 403 if no token is configured or the token is wrong, with the same body either way;
  - 409 on `CheckBusy`;
  - its own `RateLimiter(per_minute=2, per_day=50)`, keyed by `client_ip()`;
  - it runs `run_check("manual")` in the threadpool (a sync route).
  - Add smoke tests covering: no token configured gives 403, a wrong token gives 403, the right token gives 200 with a summary (fake fetch), busy gives 409, and a third call within a minute gives 429.

---

## Phase 6: User Story 4 - Demonstrate an alert (P2)

- [ ] T218 [US4] Add `run_demo(settings) -> CheckSummary` to `src/weather_risk/alerts/service.py` (no fetch; `previous = simulate_previous(current)`; a `kind='demo'` check; `is_demo` alerts; no score records). Add `wra alerts demo`, and `POST /api/alerts/demo` with the same auth, 409 and 429 rules as T217. Add smoke tests covering:
  - the demo gives exactly 2 alerts, Dallas heat +7.5 and Houston hurricane −5.0, all `is_demo`;
  - afterwards, `GET /api/rankings` is byte-identical to before;
  - a following real check (fake fetch, unchanged data) gives 0 alerts.
- [ ] T219 [US4] Create `scripts/alert_demo.py <base-url> [--check]`, per contracts/cli.md: it reads `ALERT_ADMIN_TOKEN` through `get_settings()`, uses an SSL context from the OS store, never prints the token, and exits 1 with no token and 2 on a non-200 response. Generate the token into `.env` with `secrets.token_urlsafe(32)`, without printing it (append only if absent).

---

## Phase 7: Polish & Cross-Cutting

- [ ] T220 Run the full verification, recording the output:
  - `uv run python -m pytest`, all green;
  - `uv run ruff check src scripts tests`;
  - `uv run python -m weather_risk eval`, expecting 20/20 (FR-218, SC-205). Run this **before** the local `alerts check`, which writes `data/live`, so the evals run on the seed;
  - locally, `python -m weather_risk alerts demo`, then `alerts list`, then `alerts check` twice (a baseline, then 0 alerts); afterwards delete `data/live/` so local runs return to the seed.
- [ ] T221 Code review of the 002 diff with the `code-reviewer` agent, plus a security pass on the token, the webhook and the SQL (`backend-api-security`). Fix confirmed findings test-first, and log them in `docs/decisions.md`.
- [ ] T222 Update `docs/architecture.md` (the alerts component, SQLite storage, the scheduler, the `/alerts` page) and the README (an alerts section: config variables, demo flow, limits such as slow drift and no catch-up). Railway variables and the redeploy are covered in the later step 4, not here.

---

**Verified outside this task list:** SC-202 (a live demo alert within 1 minute) and SC-203 (alerts survive a redeploy) need the deployed service. They are checked in deploy step 4, using `quickstart.md` "Validate on Railway".

---

## Dependencies & Execution Order

- Phase 1 comes first, then Phase 2. T203 is independent of T204-T207.
- US1 (T208-T213) needs T205 and T207. US2 (T214-T216) needs T207, and its data comes from T210. US3 (T217) needs T210. US4 (T218-T219) needs T210 and T214.
- Polish runs last.
- Within a TDD pair, the test task comes before the implementation, and the failure is seen first.

## Parallel Examples

- T202 ∥ T201; T204 ∥ T206 ∥ T203 (different files); T208 ∥ T210's design reading.
- In practice this is one implementer working sequentially; [P] only marks file independence.

## Implementation Strategy

1. **MVP = Phases 1 to 3 (US1):** `wra alerts check` records history and delivers. This is shippable even if the rest slips.
2. Next, US2 (the list API and page), which makes the feature visible.
3. Then US3 and US4: the protected trigger, the demo, and the script for the interview.
4. Then polish: tests, evals 20/20, reviews, docs.

## Notes

- Never print or commit `.env` values. The webhook URL and the token are `SecretStr`.
- The agent (chat) gets no new tool. `agent/` and `scoring/` files must not change in this feature.
