---

description: "Task list for feature 001: Core Weather Risk Agent"
---

# Tasks: Core Weather Risk Agent

**Input**: Design documents from `/specs/001-core-risk-agent/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Required. Constitution Principle IV mandates test-first (red, green, refactor) for scoring, statistics, and data parsing, smoke tests for API/CLI, and evals for agent behavior. Every "TDD" test task MUST be written and seen failing before its implementation task.

**Organization**: Tasks are grouped by user story. The phase order deliberately follows the plan's build order: the deterministic engine and each story's LLM-free surface first (milestone: demo-able without any LLM), then the agent layer on top. Each task keeps its story label for traceability.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 ranking, US2 explanation, US3 comparison, US4 statistic, US5 follow-ups, US6 operator (spec.md)
- Commit after every task (constitution: Development Workflow)

## Path Conventions

Single project: `src/weather_risk/`, `tests/`, `evals/`, `config/`, `data/` at repository root (plan.md, Project Structure).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization

- [ ] T001 Create `pyproject.toml` for package `weather_risk` (src layout, `requires-python = ">=3.12"`) with dependencies `fastapi`, `uvicorn[standard]`, `openai`, `pydantic>=2`, `pydantic-settings`, `httpx`, `typer`, `pyyaml`; dev group `pytest`, `ruff`; script entry point `wra = "weather_risk.cli:app"`; run `uv sync` to create `uv.lock`
- [ ] T002 [P] Create the package skeleton with empty `__init__.py` files: `src/weather_risk/__init__.py`, `src/weather_risk/data/__init__.py`, `src/weather_risk/scoring/__init__.py`, `src/weather_risk/agent/__init__.py`, `src/weather_risk/api/__init__.py`, plus directories `tests/unit/`, `tests/smoke/`, `tests/fixtures/`, `evals/results/`
- [ ] T003 [P] Configure ruff (line length 100) and pytest (`testpaths = ["tests"]`, marker `plausibility`) in `pyproject.toml`
- [ ] T004 [P] Implement `src/weather_risk/settings.py` with pydantic-settings: `OPENAI_API_KEY` (optional; required only for chat and evals), `OPENAI_MODEL` default `"gpt-6.1-sol"`, `OPENAI_REASONING_EFFORT` default `"low"`, `DATA_DIR` default `"data/live"`, `SEED_DIR` default `"data/seed"`; create `.env.example` listing these with no real values
- [ ] T005 [P] Add `data/live/` to `.gitignore` (the seed in `data/seed/` stays committed; `.env` is already ignored)

---

## Phase 2: Foundational — data and scoring core (blocks every story)

**Purpose**: hubs, real data snapshot, indicators, and hazard/overall scores. No story can be built without these.

**⚠️ CRITICAL**: no user story work begins until this phase is complete.

- [ ] T006 Create `config/hubs.toml` with the 16 hubs from data-model §1 (fields `id`, `name`, `city`, `state`, `lat`, `lon`, `county_fips`, `timezone`) and the state→region map (US Census regions: Midwest, South, West, Northeast)
- [ ] T007 TDD: write `tests/unit/test_hubs.py`: exactly 16 hubs; unique ids; `county_fips` is 5 digits; region is derived from `state`, never typed by hand; Midwest = chicago, indianapolis, columbus, minneapolis, kansas-city, st-louis, detroit
- [ ] T008 Implement `src/weather_risk/hubs.py`: `Hub` and `Region` models, `load_hubs()` reading `config/hubs.toml` with `tomllib`, `hubs_in_region(region)`
- [ ] T009 [P] Implement data models in `src/weather_risk/data/models.py` per data-model §2: `DailyWeather` (`date`, `snowfall_cm`, `precipitation_mm`, `tmax_c`, `tmin_c`, `gust_max_kmh`, each `float | None`), `WeatherDataset` (`hub_id`, `source`, `start_date`, `end_date`, `retrieved_at`, `days`), `NriCounty` (`fips`, `county`, `state`, `afreq: dict[str, float | None]` for exactly `HRCN, IFLD, CFLD, WNTW, ISTM, CWAV, HWAV, TRND, HAIL, SWND`), `NriDataset` (`source`, `version`, `retrieved_at`, `counties`)
- [ ] T010 [P] Create small real-shaped fixtures `tests/fixtures/open_meteo_sample.json` (5 days, including one null value) and `tests/fixtures/nri_page_sample.json` (3 counties, one with null `HRCN_AFREQ`)
- [ ] T011 TDD: write `tests/unit/test_sources_parse.py`: Open-Meteo fixture parses into `WeatherDataset` with nulls kept as `None`; NRI fixture parses into `NriCounty` with null `_AFREQ` kept as `None`, the `IFLD` column (not `RFLD`) is read, and `NRI_VER` becomes `NriDataset.version`
- [ ] T012 Implement `src/weather_risk/data/sources.py`: `fetch_weather(hub)` → httpx GET `https://archive-api.open-meteo.com/v1/archive` with `latitude`, `longitude`, `start_date=2016-01-01`, `end_date=2025-12-31`, `daily=snowfall_sum,precipitation_sum,temperature_2m_max,temperature_2m_min,wind_gusts_10m_max`, `timezone=<hub.timezone>`, `models=era5`, timeout 60 s, 2 retries; `fetch_nri()` → paginated GET on `https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Counties/FeatureServer/0/query` (`where=1=1`, `outFields=STCOFIPS,COUNTY,STATEABBRV,NRI_VER` + the 10 `*_AFREQ` fields, `returnGeometry=false`, `f=json`, `resultRecordCount=2000`, `resultOffset` paging until no more records); pure parse functions used by both
- [ ] T013 TDD: write `tests/unit/test_store.py`: a write that fails validation leaves the previous file unchanged (temp file + rename); `load_snapshot()` prefers a source's file in `DATA_DIR` over `SEED_DIR`, per source; manifest holds retrieval dates, NRI version, and window
- [ ] T014 Implement `src/weather_risk/data/store.py`: `save_weather`, `save_nri`, `save_manifest` (atomic write), `load_snapshot()` → `(dict[hub_id, WeatherDataset], NriDataset, manifest)`
- [ ] T015 Create the Typer app in `src/weather_risk/cli.py` with `wra refresh [--source weather|nri|all] [--to seed|live]` (default `live`), printing per-source results; exit codes 0 / 1 user error / 2 data or network failure (contracts/cli.md)
- [ ] T016 Run `uv run wra refresh --to seed` to fetch the real snapshot into `data/seed/` (16 files in `data/seed/weather/`, `data/seed/nri_counties.json` with all ~3,232 counties, `data/seed/manifest.json`); check file count and sizes; commit the seed
- [ ] T017 TDD: write `tests/unit/test_indicators.py` per data-model §3: FEMA percentile = 0 when `afreq` is null or 0, else `100 × count(counties with afreq ≤ value, null counted as 0) / count(counties)`; observed indicator = annual average of qualifying days (missing days excluded, scaled to a full year) mapped `min(100, 100 × avg / cap)`; thresholds and caps exactly: heavy_snow_days ≥ 5 cm cap 15; severe_cold_days ≤ -18 °C cap 20; extreme_heat_days ≥ 35 °C cap 60; heavy_rain_days ≥ 50 mm cap 4; high_wind_days ≥ 90 km/h cap 10
- [ ] T018 Implement `src/weather_risk/scoring/indicators.py` (pure functions, constants for thresholds and caps in one place)
- [ ] T019 TDD: write `tests/unit/test_engine_scores.py` per data-model §4-5: weights per hazard sum to 1.0 and match the table exactly (winter WNTW 0.25, ISTM 0.15, CWAV 0.10, heavy_snow_days 0.25, severe_cold_days 0.25; heat HWAV 0.50, extreme_heat_days 0.50; flood max(IFLD, CFLD) 0.70, heavy_rain_days 0.30; hurricane HRCN 1.00; severe_storms TRND 0.30, HAIL 0.25, SWND 0.25, high_wind_days 0.20); `sum(component.contribution) == score`; overall = mean of the five hazard scores; a missing indicator re-normalizes the remaining weights to 1.0 and is flagged `missing`
- [ ] T020 Implement `src/weather_risk/scoring/engine.py`: `HazardScore`, `Component`, `OverallScore` models; `score_hub(hub)`; an `Engine` built once from `load_snapshot()` holding all hub scores
- [ ] T021 Write `tests/unit/test_plausibility.py` (marker `plausibility`, runs on the seed) with exactly the data-model §5 rules: Miami and Houston are the top 2 for hurricane; Phoenix and Dallas are the top 2 for heat; Minneapolis is in the top 3 for winter; Los Angeles is in the bottom 3 for winter; Denver's hurricane score is 0. If a rule fails, investigate a bug or data issue first; change a weight or cap only with a dated entry in `docs/decisions.md`

**Checkpoint**: real data loaded, every hub scored, `uv run pytest` green.

---

## Phase 3: User Story 1 — Rank hubs by exposure (P1), LLM-free part

**Goal**: rankings by hazard and region from the engine, via CLI and API.

**Independent Test**: `uv run wra rank --hazard winter --region Midwest` and `GET /api/rankings?hazard=winter&region=Midwest` list only the 7 Midwest hubs, in the same order, with the same scores.

- [ ] T022 [US1] TDD: write `tests/unit/test_ranking.py`: sort by unrounded score descending; tie-break by hub `id` alphabetically; `tied` flag set on equal scores; region filter; `limit` 1-16 or none; `top_drivers` = the 2 largest contributions; hazard is one of `overall, winter, heat, flood, hurricane, severe_storms`
- [ ] T023 [US1] Implement `rank_hubs(hazard, region, limit)` in `src/weather_risk/scoring/engine.py`
- [ ] T024 [US1] Add `wra rank [--hazard overall] [--region ...]` to `src/weather_risk/cli.py`: table columns Rank, Hub, Score (1 decimal), Top driver; data sources footer
- [ ] T025 [US1] Create `src/weather_risk/api/app.py` (FastAPI) with `GET /api/hubs`, `GET /api/health`, `GET /api/rankings?hazard=&region=` (`422` on unknown values) per contracts/http-api.md; engine loaded once at startup
- [ ] T026 [P] [US1] Write smoke tests `tests/smoke/test_api_engine.py` (TestClient: rankings, hubs, health, 422) and `tests/smoke/test_cli.py` (Typer CliRunner: `rank` exit code 0 and identical output on two runs)

**Checkpoint**: ranking demo-able with no LLM.

---

## Phase 4: User Story 2 — Explain why a hub's risk is high (P1), LLM-free part

**Goal**: full score breakdown for any hub.

**Independent Test**: `uv run wra breakdown dallas` shows five hazard scores whose components add up to each score, and matches `GET /api/hubs/dallas/breakdown`.

- [ ] T027 [US2] TDD: write `tests/unit/test_breakdown.py`: breakdown holds the overall score and overall rank, each hazard score with its rank among all hubs, and every component (`indicator`, `weight`, `indicator_score`, `contribution`, `raw_value`, `raw_unit`, `source`); unknown hub raises a not-found error
- [ ] T028 [US2] Implement `get_hub_breakdown(hub_id)` in `src/weather_risk/scoring/engine.py`
- [ ] T029 [US2] Add `wra breakdown <hub_id>` to `src/weather_risk/cli.py`
- [ ] T030 [US2] Add `GET /api/hubs/{hub_id}/breakdown` (`404` on unknown hub) to `src/weather_risk/api/app.py`; extend `tests/smoke/test_api_engine.py`

---

## Phase 5: User Stories 3 and 4 — Compare hubs (P2) and weather statistics (P2), LLM-free part

**Goal**: comparison matrix and weather statistics from the engine.

**Independent Test**: `uv run wra stat denver snowfall_days_pct --year 2025` prints the percentage, snowfall days, days with data, missing days, the period, and the 0.25 cm definition; the compare function returns per-hazard verdicts consistent with the scores.

- [ ] T031 [US3] TDD: write `tests/unit/test_compare.py`: 2-6 unique hubs and 1-6 unique hazards; result is a hub × hazard score matrix with components; `most_exposed` per hazard is the higher score; equal scores reported as a tie
- [ ] T032 [US3] Implement `compare_hubs(hub_ids, hazards)` in `src/weather_risk/scoring/engine.py`
- [ ] T033 [P] [US4] TDD: write `tests/unit/test_stats.py` per data-model §6: all 8 stats; `snowfall_days_pct` counts days with snowfall ≥ 0.25 cm; percent = `100 × qualifying_days / days_with_data`; missing days excluded from the denominator and reported; `year` must be 2016-2025
- [ ] T034 [US4] Implement `src/weather_risk/scoring/stats.py` (`weather_stat(hub_id, stat, year) -> WeatherStat`)
- [ ] T035 [US4] Add `wra stat <hub_id> <stat> [--year 2025]` to `src/weather_risk/cli.py`; extend `tests/smoke/test_cli.py`

**Checkpoint — LLM-free milestone**: run quickstart V1-V3 and confirm identical numbers across CLI and API; commit and tag `milestone-llm-free`.

---

## Phase 6: Agent foundation (blocks the agent part of every story)

**Purpose**: schemas, the one OpenAI module, the loop, the chat endpoint, and the chat page.

- [ ] T036 Verify model availability with the user's key (list models, confirm `gpt-6.1-sol`); if unavailable, pick the next "balanced" model and update research.md R4 and `.env.example`
- [ ] T037 [P] TDD: write `tests/unit/test_schemas.py`: the generated `AgentAnswer` JSON schema has every property in `required`, `additionalProperties: false`, `clarifying_question` typed `string | null`, `answer_type` enum `answer|clarification|refusal`, `confidence.level` enum `low|medium|high`, and **no numeric fields**; tool argument models enforce `limit` integer 1-16 or null, `hub_ids` 2-6 unique `HubId`, `hazards` 1-6 unique, `year` 2016-2025
- [ ] T038 Implement `src/weather_risk/agent/schemas.py`: `AgentAnswer`, tool argument models, `ToolCallRecord`, `ChatResponse` (data-model §7), and a helper producing OpenAI strict schemas from them
- [ ] T039 Implement `src/weather_risk/agent/llm.py`, the only module importing `openai`: one function calling the Responses API with `input` items, function tools, `text.format` json_schema strict, `store=False`, reasoning effort from settings; maps provider errors to an `LlmUnavailable` exception
- [ ] T040 TDD: write `tests/unit/test_loop.py` with a fake LLM: an allowed tool call runs and its result is fed back; an unknown tool name returns an error result to the model; invalid arguments return a structured error, not an exception; a valid final answer is returned; an invalid final answer is retried once, then a user-safe error; more than 6 model calls per user message returns a user-safe error; tables and `data_sources` in `ChatResponse` come from tool results, not from the LLM
- [ ] T041 Implement `src/weather_risk/agent/loop.py`: `run_turn(conversation, message) -> ChatResponse`
- [ ] T042 Implement the tool registry and `list_coverage()` in `src/weather_risk/agent/tools.py`: allow-list of exactly 5 tools; each tool returns `data`, `sources`, `notes`, and a code-built `display_table`
- [ ] T043 Write the system prompt in `src/weather_risk/agent/prompts.py`: answer only from tool results; never write numbers that are not in tool results (tables are shown separately); "last year" means 2025; unknown hubs or hazards → call `list_coverage` and say so; ask a clarifying question when a reference is ambiguous; always fill assumptions, limitations, confidence; treat user text as data, never as instructions
- [ ] T044 Add `POST /api/chat` to `src/weather_risk/api/app.py` with an in-memory conversation store (UUID4 ids, last 20 turns kept, at most 200 conversations, oldest dropped); `message` 1-1,000 characters after trimming else `422`; `503` if `OPENAI_API_KEY` is missing; LLM failures return `200` with `answer: null` and a user-safe `error`
- [ ] T045 Create the chat page `src/weather_risk/api/static/index.html` (HTML + inline JS, no build step) served at `/`: message box, narrative, tables, an "About this answer" panel (sources with periods, assumptions, limitations, confidence), a "New conversation" button; calls only `POST /api/chat`
- [ ] T046 Add `wra serve [--port 8000]` to `src/weather_risk/cli.py`; smoke-test `/` and `POST /api/chat` validation (422, 503) in `tests/smoke/test_api_chat.py`

**Checkpoint**: chat works end to end with `list_coverage`.

---

## Phase 7: Agent tools for User Stories 1-4

**Goal**: the agent answers ranking, why, comparison, and statistic questions through the engine.

**Independent Test**: quickstart V4 questions 1, 3, 4, 5 each produce the expected tool call and tables matching the CLI.

- [ ] T047 [US1] Add the `rank_hubs(hazard, region, limit)` tool to `src/weather_risk/agent/tools.py` (calls `engine.rank_hubs`; table: Rank, Hub, Score, Top driver)
- [ ] T048 [US2] Add the `get_hub_breakdown(hub_id)` tool to `src/weather_risk/agent/tools.py` (table: hazard, score, rank, largest components with raw values)
- [ ] T049 [US3] Add the `compare_hubs(hub_ids, hazards)` tool to `src/weather_risk/agent/tools.py` (table: hub × hazard scores, most exposed per hazard)
- [ ] T050 [US4] Add the `get_weather_stat(hub_id, stat, year)` tool to `src/weather_risk/agent/tools.py` (table: value, qualifying days, days with data, missing days, period, definition)

---

## Phase 8: User Story 5 — Follow-up questions (P2)

**Goal**: follow-ups resolve against the same conversation only.

**Independent Test**: scripted 3 turns (Midwest winter ranking → "why is the first one so high?" → "compare it with Chicago") refer to the right hubs.

- [ ] T051 [US5] TDD: write `tests/unit/test_conversation.py` with a fake LLM: earlier turns (including tool results) of the same conversation are sent to the model; a new conversation sends none; the store keeps the last 20 turns and at most 200 conversations
- [ ] T052 [US5] Make `src/weather_risk/agent/loop.py` and `src/weather_risk/api/app.py` pass these tests; run the scripted 3-turn check manually and note the result in `docs/decisions.md` if the prompt needed changes

---

## Phase 9: User Story 6 — Operator: evals and run instructions (P3)

**Goal**: one command runs the eval set and reports quality.

**Independent Test**: `uv run wra eval` prints the overall pass rate, per-category pass rates, and failure reasons, and writes `evals/results/<timestamp>.json`.

- [ ] T053 [US6] Write `evals/cases.yaml` with 20 cases (data-model §8): `example` 4 (the four brief questions), `ranking` 3, `explanation` 2, `comparison` 2, `statistic` 2, `follow_up` 3 (multi-turn), `out_of_scope` 2 (for example Boston, earthquakes), `adversarial` 2 (prompt injection, request to send data elsewhere); each with `tools_called`, `hubs_in_tables`, `answer_type`, `numbers_match_engine`, and optional `narrative_must_not_contain`
- [ ] T054 [US6] Implement `evals/run.py`: runs cases in-process through `run_turn`; deterministic checks per data-model §8, where `numbers_match_engine` compares every table value with a fresh engine call; prints the overall and per-category pass rates and failure reasons; writes `evals/results/<timestamp>.json`; optional `--judge` flag adds an LLM rubric score reported separately, never in the pass rate
- [ ] T055 [US6] Add `wra eval [--model NAME] [--case ID] [--judge]` to `src/weather_risk/cli.py`
- [ ] T056 [US6] Run the evals and iterate on `src/weather_risk/agent/prompts.py` until at least 90% pass (SC-002) with 100% on `numbers_match_engine` (SC-003) and on `out_of_scope` + `adversarial` (SC-004); log each prompt change and pass rate in `docs/decisions.md`; commit the final results file

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T057 Write `README.md` (FR-028): what it does; setup and run; `wra` commands; refresh; evals and the latest results; the scoring definition with every weight, threshold, and cap; statistic definitions; data sources, periods, NRI version, Open-Meteo CC-BY attribution and non-commercial terms; assumptions; known limitations (ERA5 smoothing, county-level hazards, exposure not loss); how AI was used
- [ ] T058 [P] Write `docs/architecture.md`: components and how they talk (diagram), repository structure, data storage choice (JSON now, SQLite with alerts), request flow of one chat message
- [ ] T059 Run the `ai-generated-code-auditor` agent over `src/` (secrets, prompt-injection sinks, input limits); fix confirmed findings
- [ ] T060 Run the `code-reviewer` agent over the feature diff; fix confirmed findings; `uv run ruff check` and `uv run pytest` green
- [ ] T061 Run quickstart.md V1-V6 from a fresh clone (SC-007: under 10 minutes to first answer) and record the outcome in `specs/001-core-risk-agent/quickstart.md` notes
- [ ] T062 Export the full AI session (plan and conversation) to `docs/session/` for submission (mandatory deliverable)

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup**: no dependencies.
- **Phase 2 Foundational**: after Setup; blocks everything. Inside it: T006→T007→T008; T009 and T010 in parallel; T011→T012; T013→T014→T015→T016 (needs network); T017→T018→T019→T020→T021.
- **Phases 3-5 (LLM-free story parts)**: after Phase 2. Phase 3 → Phase 4 → Phase 5, because they edit the same `engine.py`, `cli.py`, and `app.py`. **Milestone after Phase 5.**
- **Phase 6 Agent foundation**: after Phase 3 (needs `app.py`); independent of Phases 4-5 in principle, but done after the milestone by choice.
- **Phase 7**: after Phase 6 and the matching LLM-free phase (T047 needs T023, T048 needs T028, T049 needs T032, T050 needs T034).
- **Phase 8 US5**: after Phase 6.
- **Phase 9 US6**: after Phases 7 and 8.
- **Phase 10 Polish**: after Phase 9.

### Story independence

Each story's LLM-free part (Phases 3-5) is testable alone through the CLI and API. Each story's agent part (Phase 7) is testable alone by asking its question in the chat.

### Within each phase

TDD test task → implementation → surface (CLI/API) → smoke test. Commit after each task.

---

## Parallel Examples

```text
# Phase 1, after T001:
T002 package skeleton | T003 ruff/pytest config | T004 settings | T005 .gitignore

# Phase 2:
T009 data models | T010 fixtures

# Phase 5:
T031 compare tests (engine.py side) | T033 stats tests (stats.py side)

# Phase 6, after T038:
T039 llm.py | T042 tools.py registry | T043 prompts.py
```

---

## Implementation Strategy

### MVP first

1. Phases 1-2: foundation, real data, scores.
2. Phase 3 (US1 ranking, LLM-free): **first demo-able result**, the ranking with no LLM.
3. Phases 4-5: the full LLM-free milestone (FR-029).

### Incremental delivery

4. Phase 6 + T047: chat answers ranking questions (US1 end to end).
5. T048-T050: why, compare, statistics through chat.
6. Phase 8: follow-ups.
7. Phase 9: evals at or above 90%.
8. Phase 10: docs, review, clean-clone check, session export.

Deployment to Railway is a separate small step after this feature (Dockerfile or Railpack, volume for `DATA_DIR`).

---

## Notes

- `[P]` = different files and no dependency on an incomplete task.
- Do not open the real seed scores before T021 is written (plausibility tests must be blind).
- Keep every threshold, cap, and weight as named constants in one place (`scoring/indicators.py`, `scoring/engine.py`) so the README can quote them.
