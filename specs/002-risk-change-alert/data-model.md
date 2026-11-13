# Data Model: Risk-Change Alert

All tables live in `DATA_DIR/alerts.sqlite`. Times are UTC ISO-8601 strings (`2026-11-13T18:00:00Z`).

## 1. Watched scores

`watched_scores(engine) -> dict[hub_id, dict[metric, float]]`, where `metric` is one of `overall, winter, hurricane, flood, heat, severe_storms` (the 001 `METRICS`). The values are `round(engine.metric_score(hub, metric), 1)`. That gives 16 × 6 = 96 values.

## 2. Detection rule (pure, test-first)

`detect_changes(previous, current, threshold) -> list[Change]`

- For every hub in **both** `previous` and `current`, and every metric in both: `change = round(current - previous, 1)`. Emit `Change(hub_id, metric, old, new, change)` when `abs(change) >= threshold`.
- A hub only in `current` (new hub) gives no change; it becomes part of the baseline. A hub only in `previous` (removed hub) gives no change.
- `previous` empty (first check) gives `[]`; the check is marked `baseline=1`.
- Output order is sorted by `(hub_id, metric)`, so it is deterministic.
- Validation: `threshold > 0`.

`simulate_previous(current) -> previous`: a deep copy with `dallas.heat -= 7.5` and `houston.hurricane += 5.0` (rounded to 1 decimal; a shift that would leave 0-100 is applied in the other direction instead), giving exactly 2 changes at the default threshold of 2.0. If a hub or metric is missing, that shift is skipped.

## 3. Tables

### `checks`

| Column | Type | Rule |
|---|---|---|
| id | INTEGER PK | autoincrement |
| kind | TEXT | `scheduled`, `manual`, or `demo` |
| started_at, finished_at | TEXT | UTC ISO |
| status | TEXT | `ok` or `failed` (a failure inside the check itself, e.g. scoring error) |
| baseline | INTEGER | 1 if there was no previous real check |
| hubs_checked | INTEGER | |
| alerts_raised | INTEGER | |
| fetch_failures | TEXT | JSON list of `"weather:dallas"`, `"nri"`; empty for demo |
| data_retrieved | TEXT | JSON of the engine's `data_sources()` after the fetch |

### `score_records` (real checks only, never demo)

| Column | Type | Rule |
|---|---|---|
| check_id | INTEGER FK → checks.id | |
| hub_id, metric | TEXT | |
| value | REAL | one decimal |
| | | PK (check_id, hub_id, metric) |

**Last real scores:** the records of `MAX(id) FROM checks WHERE kind != 'demo' AND status = 'ok'`.

**Retention:** after each real check, delete the records of checks older than the newest 30 real checks.

### `alerts`

| Column | Type | Rule |
|---|---|---|
| id | INTEGER PK | |
| check_id | INTEGER FK | |
| hub_id, metric | TEXT | |
| old_value, new_value, change | REAL | from `detect_changes` |
| detected_at | TEXT | the check's `started_at` |
| is_demo | INTEGER | 1 for demo |
| data_retrieved | TEXT | JSON copy from the check |
| delivery_status | TEXT | `pending` (only while sending), `delivered`, `failed`, or `not_configured` |
| delivery_error | TEXT NULL | e.g. `HTTP 500`, `ConnectTimeout`; never the URL |

## 4. Lifecycle of one check

1. Take the lock, or return busy.
2. Real check: `fetch_all(DATA_DIR)`, mark the refresh complete, and build the engine. Demo: build the engine from current data, with no fetch.
3. `current = watched_scores(engine)`. `previous` = the last real scores (real check), or `simulate_previous(current)` (demo).
4. `changes = detect_changes(previous, current, threshold)`.
5. In one transaction: insert the check row, the score records (real only) and the alert rows with `delivery_status='not_configured'` or `'pending'`. Then prune.
6. Outside the transaction: for each alert, log it, deliver it if a URL is configured, and update `delivery_status` and `delivery_error`.
7. Release the lock and return a summary (see the contracts).

A failure in step 2 for one source is recorded in `fetch_failures`, and the old data is kept. If scoring itself fails, the check is recorded as `failed` with no score records, so the next check compares with the last good one.
