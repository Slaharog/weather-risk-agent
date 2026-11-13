# Research: Core Weather Risk Agent

**Feature**: 001-core-risk-agent | **Date**: 2026-11-13

Every fact below was checked live on 2026-11-13 (API calls or official docs), not taken from memory.

## R1. Observed weather source

- **Decision**: Open-Meteo Historical Weather API (`https://archive-api.open-meteo.com/v1/archive`), `models=era5`, daily variables `snowfall_sum` (cm), `precipitation_sum` (mm), `temperature_2m_max` / `temperature_2m_min` (°C), `wind_gusts_10m_max` (km/h), with the hub's local `timezone`. One request per hub covering the whole window.
- **Window**: 2016-01-01 to 2025-12-31 (10 full years) for scoring baselines. "Last year" questions use 2025.
- **Rationale**: no API key, verified working (Denver test call returned 200 with all five variables). Reanalysis is gap-free, so there are no station outages to handle. Open-Meteo's own docs advise ERA5 alone for multi-year analysis, for consistency across model upgrades.
- **Constraints found**: free tier is non-commercial only, under 10,000 calls/day, CC-BY 4.0 attribution required. Our use (16 calls per refresh, interview demo) is well within it. A production deployment for a logistics company would need Open-Meteo's commercial plan; this goes in the README limitations.
- **Known weakness**: ERA5 is a ~25 km grid model. It smooths local extremes, especially convective wind gusts and very local snow bands. Stated as a limitation; it is the reason storm and flood scores lean on FEMA event history rather than on gusts and rainfall alone.
- **Alternatives considered**: NOAA NCEI station data (Climate Data Online) needs a token, has station gaps, and needs station matching per hub. NWS API only serves forecasts and current alerts, not history. Meteostat needs a key on its hosted API.

## R2. Hazard source (hurricane, flood, severe storms, plus winter and heat)

- **Decision**: FEMA National Risk Index (NRI), county level, **December 2025** release, read from FEMA's public ArcGIS FeatureServer `National_Risk_Index_Counties/FeatureServer/0` (`/query`, `f=json`, no key; max 2,000 records per page, 3,232 counties, so 2 pages).
- **Fields used**: `<HAZARD>_AFREQ` = annualized frequency (expected events per year, numeric double), for:
  `HRCN` hurricane, `IFLD` inland (riverine) flooding, `CFLD` coastal flooding, `WNTW` winter weather, `ISTM` ice storm, `CWAV` cold wave, `HWAV` heat wave, `TRND` tornado, `HAIL` hail, `SWND` strong wind. Plus `STCOFIPS`, `COUNTY`, `STATEABBRV`, `NRI_VER`.
- **Verified**: all 16 hub counties exist (for example 08031 Denver CO, 48113 Dallas TX, 12086 Miami-Dade FL). Sample: Dallas `HWAV_AFREQ` 19.1, `HAIL_AFREQ` 8.9, `ISTM_AFREQ` 1.23; Miami `HRCN_AFREQ` 0.305, `CFLD_AFREQ` 2.25; Denver `HRCN_AFREQ` null.
- **Null handling**: a null `_AFREQ` means FEMA considers the hazard not applicable to that county (for example hurricanes in Denver). It is treated as frequency 0 and the answer says so. This differs from missing data, which only happens if a source fails.
- **Why frequency, not FEMA's own Risk Score**: NRI `_RISKS` multiplies hazard by building value, population, social vulnerability and resilience. That measures a county's total loss potential, so large, wealthy counties score high whatever the weather. We want **exposure of one hub at that location**, which is the hazard frequency. This is an interview-worthy decision.
- **Naming change found**: older NRI versions used `RFLD` for riverine flooding; the December 2025 release uses `IFLD` (inland flooding). Code must use `IFLD` and record `NRI_VER`.
- **Alternatives considered**: NOAA Storm Events database (raw events, heavy cleaning needed), NOAA HURDAT2 hurricane tracks (needs geospatial work), FEMA flood maps (parcel-level, far too detailed for this scope).

## R3. Absolute scoring method

- **Decision**: every hazard score is a weighted mix of two kinds of 0-100 indicators, both on fixed national yardsticks:
  1. **FEMA frequency percentile**: the hub county's national percentile of `_AFREQ` among all 3,232 counties (share of counties with a strictly lower value, plus half the ties). Computed from the full national table in the snapshot, so it does not depend on our hub list.
  2. **Observed weather indicator**: an annual average from the 10-year Open-Meteo record, mapped linearly onto 0-100 between a fixed floor (0) and a fixed cap (100), clamped.
- **Rationale**: both are independent of the hub list (Q2 decision), both are reproducible from the snapshot, and the result is a transparent weighted sum (Principle I). FEMA history covers what reanalysis cannot see (hurricanes, floods, tornadoes); Open-Meteo adds direct local evidence the analyst can check ("Denver had snow on X% of days").
- **The caps are judgment calls**, documented in `data-model.md` and in the README, and listed as an assumption in answers.
- **Alternatives considered**: FEMA only (simpler, but the weather API would only serve statistics), weather only (cannot see hurricanes or floods honestly), z-scores against our 16 hubs (relative, rejected in Q2).

## R4. LLM provider, API, and model

- **Decision**: OpenAI **Responses API** via the official `openai` Python SDK. Function tools with `"strict": true`; the final answer via `text.format` with a strict `json_schema` generated from Pydantic, then validated again with Pydantic.
- **Model**: default `gpt-6.1-sol`, read from the `OPENAI_MODEL` environment variable. OpenAI's models page (checked 2026-11-13) recommends GPT-6 Astra as flagship, **GPT-6.1 Sol "to balance intelligence and cost"**, and GPT-6 Luna for cost-sensitive volume. Sol fits a tool-using agent with a small eval budget. The eval runner can be pointed at Luna to compare cost and pass rate.
- **Sampling**: current models are reasoning models configured with `reasoning_effort` rather than `temperature`. We use a low reasoning effort and keep the deterministic checks as the primary eval signal. This adapts the constitution's "low temperature" wording to what the API supports; the intent (lowest variance) is kept.
- **Strict schema rules found**: in strict mode every field must be listed as `required` and `additionalProperties` must be `false`; optional values are expressed as a union with `null`. Our Pydantic models follow this.
- **State**: we keep the conversation history ourselves and send it each turn (`store=false`), instead of `previous_response_id`. Rationale: the provider stays swappable (Principle II) and the history is inspectable in the eval runner.
- **To verify at implementation start**: list models with the user's key and confirm `gpt-6.1-sol` is available; fall back to the next "balanced" model if not.

## R5. Conversation memory

- **Decision**: in-process dictionary keyed by `conversation_id`, holding the last 20 turns, capped at 200 conversations (oldest dropped). Lost on restart.
- **Rationale**: the spec says conversations need not persist across restarts; single demo service. Simplest thing that works.
- **Alternatives considered**: SQLite (needed only if conversations must survive restarts), OpenAI stored responses (ties state to the provider).

## R6. Storage

- **Decision**: no database in this feature. Raw API responses are JSON files: the committed seed snapshot in `data/seed/`, and refreshed data in `DATA_DIR` (a Railway volume in production). On startup the app loads the newest complete snapshot into memory and computes all scores (16 hubs; milliseconds).
- **Rationale**: the seed must be plain files in git anyway, and nothing in this feature needs queries or history. SQLite arrives with spec 002 (score history for alerts). This is a justified deviation from the constitution's "SQLite unless the plan justifies otherwise" (see the plan's Complexity Tracking).
- **Atomic refresh**: refresh writes each source to a temporary file and renames it into place only after validation. A failed source keeps its previous file (FR-008).

## R7. Interface, CLI, and evals

- **API**: FastAPI, one process; serves `/api/*` and the static chat page at `/`.
- **CLI**: one entry point, `wra`, with `rank`, `breakdown`, `stat`, `refresh`, `eval`. It calls the same scoring functions as the API and the agent tools (FR-029).
- **Chat page**: one HTML file, plain JavaScript, no build step.
- **Evals**: cases in `evals/cases.yaml`; the runner calls the agent in-process (no HTTP needed), records tool calls, and checks expectations deterministically. Results go to `evals/results/<timestamp>.json` and a printed summary.
- **Dependencies**: `fastapi`, `uvicorn`, `openai`, `pydantic`, `pydantic-settings`, `httpx`, `typer`, `pyyaml`; dev: `pytest`, `ruff`. Python 3.12 (installed locally), managed by `uv`.

## R8. Hub locations

- **Decision**: city-center coordinates and the county FIPS for each hub, stored in `config/hubs.toml` (read with the standard library `tomllib`). Regions follow US Census Bureau regions. All FIPS codes were verified against NRI.
- **Assumption**: real hubs sit on city outskirts; at 25 km grid resolution and county-level hazard data, the difference does not change the result.
