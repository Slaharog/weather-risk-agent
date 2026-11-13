# Implementation Plan: Core Weather Risk Agent

**Branch**: `001-core-risk-agent` | **Date**: 2026-11-13 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-core-risk-agent/spec.md`

## Summary

Build a deterministic weather-exposure engine for 16 US hubs, with a conversational agent on top. The engine combines two public, keyless sources: FEMA National Risk Index county event frequencies, as national percentiles, and 10 years of Open-Meteo ERA5 daily weather, as fixed-scale indicators. It produces five hazard scores and an overall score per hub, each a transparent weighted sum. The scores, rankings, breakdowns, and statistics are plain Python, available without any LLM through a CLI and API endpoints.

An OpenAI agent, built as a hand-written Responses API loop with five strict, read-only tools, answers ranking, "why", comparison, statistic, and follow-up questions. Its final answer is a strict JSON schema (narrative, assumptions, limitations, confidence). Code renders all numbers and attaches the data sources. FastAPI serves the API and a one-file chat page. A YAML eval set of about 20 cases runs with `wra eval`, using deterministic checks.

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**: FastAPI, Uvicorn, `openai` SDK (Responses API), Pydantic v2, pydantic-settings, httpx, Typer, PyYAML. Dev: pytest, ruff.

**Storage**: JSON files. The committed seed snapshot is in `data/seed/`. Refreshed data goes to `DATA_DIR`, which is a Railway volume in production. Everything else lives in memory. No database in this feature (see Complexity Tracking).

**Testing**: pytest. Unit tests are written test-first for indicators, percentiles, scoring, ranking, and statistics. Smoke tests cover the API and CLI. Agent behavior is covered by the evals.

**Target Platform**: local Windows or Linux development; Railway (Linux container) for deployment, which comes after this feature's core.

**Project Type**: web service with a CLI (single Python package)

**Performance Goals**: chat answers within 30 seconds for 95% of questions (SC-008). LLM-free endpoints under 1 second.

**Constraints**: works offline from the data providers using the seed (SC-007). Open-Meteo non-commercial terms. At most 6 model calls per user message. Input limited to 1,000 characters.

**Scale/Scope**: 16 hubs, 5 hazards, 10 years of daily data (about 58,000 hub-days), about 3,232 NRI counties. Single-tenant demo.

All unknowns were resolved in [research.md](research.md); none remain.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan complies | Status |
|---|---|---|
| I. Deterministic scoring, LLM explains | All scores, ranks, and statistics are pure functions in `scoring/`. Tools return engine output, code renders tables, and the LLM writes only the narrative. Each score is a weighted sum with its components returned (data-model §4-5). The same functions back the CLI, the API, and the tools (FR-029). | Pass |
| II. Enforced structured contracts | Strict function tools plus a strict `text.format` JSON schema generated from Pydantic, re-validated with Pydantic, one retry, then an error. All LLM calls go through one module, `agent/llm.py`. | Pass |
| III. Grounded and honest | `AgentAnswer` requires assumptions, limitations, and confidence. Code attaches `data_sources` with periods. Unknown hubs and hazards are impossible to express in the tool enums, so the agent must use `list_coverage` and say so. | Pass |
| IV. Test-first and evals | TDD for `scoring/` and `data/` parsing. About 20 eval cases across 8 categories, run with `wra eval`. Primary checks are deterministic, including numbers matching the engine. | Pass, with one adaptation (see Complexity Tracking) |
| V. Narrow scope, explainable code | No agent framework, a loop of about 80 lines, one package, no frontend build. Alerts and voice are left to their own specs. | Pass |
| VI. Reproducible public data | Keyless public sources. A committed seed snapshot. Hubs in one config file. Atomic per-source refresh. | Pass |
| VII. Safe by default | Key from the environment, `.env` git-ignored, an allow-list of 5 read-only tools, enum-typed arguments, a length limit, and a step limit. No outbound calls are triggered by chat. | Pass |

**Post-design re-check (after Phase 1)**: still passes. The data model keeps every score decomposable (`sum(contributions) == score` is a tested rule). The contracts keep numbers out of the LLM's output (`AgentAnswer` has no numeric fields).

## Project Structure

### Documentation (this feature)

```text
specs/001-core-risk-agent/
├── plan.md              # This file
├── research.md          # Phase 0: sources, scoring method, model, storage
├── data-model.md        # Phase 1: entities, indicators, weights, statistics
├── quickstart.md        # Phase 1: run and validation guide
├── contracts/
│   ├── http-api.md      # REST endpoints
│   ├── agent-tools.md   # 5 tools, answer schema, loop rules
│   └── cli.md           # wra commands
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
config/
└── hubs.toml                  # 16 hubs, state→region map
data/
└── seed/                      # committed real API responses
    ├── manifest.json          # retrieval dates, NRI version, window
    ├── nri_counties.json      # all counties, AFREQ columns only
    └── weather/<hub_id>.json  # 16 files, daily ERA5 2016-2025
src/weather_risk/
├── settings.py                # env config (OPENAI_API_KEY, OPENAI_MODEL, DATA_DIR)
├── hubs.py                    # load hubs and regions
├── data/
│   ├── models.py              # DailyWeather, WeatherDataset, NriCounty, NriDataset
│   ├── sources.py             # Open-Meteo and FEMA NRI fetchers (refresh only)
│   └── store.py               # load newest snapshot; atomic write
├── scoring/
│   ├── indicators.py          # FEMA percentiles, observed day counts → 0-100
│   ├── engine.py              # hazard + overall scores, ranking, breakdown, compare
│   └── stats.py               # weather statistics
├── agent/
│   ├── schemas.py             # tool argument models, AgentAnswer, ChatResponse
│   ├── tools.py               # 5 tools: call engine, build display tables + sources
│   ├── prompts.py             # system prompt
│   ├── llm.py                 # the only module that talks to OpenAI
│   └── loop.py                # tool-calling loop, validation, retry, step limit
├── api/
│   ├── app.py                 # FastAPI app, routes, conversation store
│   └── static/index.html      # chat page (HTML + inline JS)
└── cli.py                     # wra rank | breakdown | stat | refresh | eval | serve
evals/
├── cases.yaml                 # ~20 cases, 8 categories
├── run.py                     # runner + deterministic checks + report
└── results/                   # timestamped JSON results (committed for submission)
tests/
├── unit/                      # indicators, percentiles, engine, stats, schemas
└── smoke/                     # API routes, CLI commands
docs/
├── decisions.md               # decision log (exists)
└── architecture.md            # design doc deliverable (written at the end)
pyproject.toml, uv.lock, .env.example, README.md
```

**Structure Decision**: a single Python package, `src/weather_risk`, with four layers that only call downward: `api`/`cli` → `agent` → `scoring` → `data`. The scoring layer never imports the agent, which keeps the deterministic engine independent of the LLM. That independence is the point of FR-029.

## Build order (input to /speckit-tasks)

1. Project skeleton (uv, settings, hubs config) and the seed snapshot fetch (`wra refresh` writes `data/seed` once).
2. Scoring engine test-first: indicators, percentiles, hazard scores, overall, ranking with tie-break, breakdown, compare, statistics.
3. LLM-free surfaces: `wra rank|breakdown|stat`, `GET /api/rankings`, `GET /api/hubs/{id}/breakdown` (JSON, browsable at `/docs`), plus the plausibility tests from data-model §5. This is a demonstrable milestone even if the agent slips.
4. Agent: schemas, tools, the LLM module, the loop, the system prompt; `POST /api/chat` with conversation memory.
5. Chat page.
6. Eval set and runner; iterate on the prompt until at least 90% pass.
7. README and architecture doc (deployment to Railway follows as its own small step).

## Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| JSON files instead of SQLite (constitution: "SQLite unless a plan justifies otherwise") | The seed must be plain files in git anyway, and this feature has no queries, history, or concurrent writers. JSON files are simpler. | Adding SQLite now adds a schema and a loader for no benefit. It arrives with spec 002, where score history needs it. |
| `reasoning_effort` instead of "low temperature" for evals (Principle IV wording) | Current OpenAI models are reasoning models configured by reasoning effort, not temperature (research R4). | Not an alternative: the parameter is not offered. The intent, lowest variance, is kept, and the deterministic checks stay primary. |
