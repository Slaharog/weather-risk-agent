# Data Model: Core Weather Risk Agent

**Feature**: 001-core-risk-agent | **Date**: 2026-11-13

All entities are Pydantic models held in memory. Raw source data is stored as JSON files (see `research.md` R6). Every number below is a documented judgment call unless it comes from a source.

## 1. Hub and Region

**Hub** (from `config/hubs.toml`)

| Field | Type | Rule |
|---|---|---|
| `id` | str | lowercase slug, unique, for example `dallas` |
| `name` | str | display name, for example "Dallas, TX" |
| `city`, `state` | str | state is a 2-letter code |
| `lat`, `lon` | float | city-center coordinates |
| `county_fips` | str | 5 digits, must exist in the NRI snapshot |
| `region` | Region | derived from `state` via the Census map, not typed by hand |
| `timezone` | str | IANA name, used for daily weather boundaries |

**Region**: `Midwest`, `South`, `West`, `Northeast` (US Census Bureau regions). A state-to-region map is part of the config.

| id | city | county (FIPS) | region |
|---|---|---|---|
| chicago | Chicago, IL | Cook (17031) | Midwest |
| indianapolis | Indianapolis, IN | Marion (18097) | Midwest |
| columbus | Columbus, OH | Franklin (39049) | Midwest |
| minneapolis | Minneapolis, MN | Hennepin (27053) | Midwest |
| kansas-city | Kansas City, MO | Jackson (29095) | Midwest |
| st-louis | St. Louis, MO | St. Louis city (29510) | Midwest |
| detroit | Detroit, MI | Wayne (26163) | Midwest |
| dallas | Dallas, TX | Dallas (48113) | South |
| houston | Houston, TX | Harris (48201) | South |
| miami | Miami, FL | Miami-Dade (12086) | South |
| atlanta | Atlanta, GA | Fulton (13121) | South |
| memphis | Memphis, TN | Shelby (47157) | South |
| denver | Denver, CO | Denver (08031) | West |
| phoenix | Phoenix, AZ | Maricopa (04013) | West |
| los-angeles | Los Angeles, CA | Los Angeles (06037) | West |
| newark | Newark, NJ | Essex (34013) | Northeast |

## 2. Source data

**DailyWeather** (per hub, from Open-Meteo): `date`, `snowfall_cm`, `precipitation_mm`, `tmax_c`, `tmin_c`, `gust_max_kmh`. Any value may be `null`; a day with a null in the variable a statistic needs is a **missing day** for that statistic.

**WeatherDataset**: `hub_id`, `source` ("Open-Meteo Historical Weather API, ERA5"), `start_date`, `end_date`, `retrieved_at`, `days: list[DailyWeather]`.

**NriCounty** (from FEMA NRI): `fips`, `county`, `state`, and one `afreq` value per NRI hazard code (`HRCN`, `IFLD`, `CFLD`, `WNTW`, `ISTM`, `CWAV`, `HWAV`, `TRND`, `HAIL`, `SWND`), each `float | null`.

**NriDataset**: `source` ("FEMA National Risk Index"), `version` (from `NRI_VER`, for example "December 2025"), `retrieved_at`, `counties: list[NriCounty]` (all ~3,232 counties, needed for national percentiles).

## 3. Indicators (the building blocks of scores)

Every indicator yields a value from 0 to 100 and keeps its **raw value** so explanations can cite it.

### 3a. FEMA frequency ratio (amended 2026-11-13; was a percentile rank)

For NRI hazard code `h` and hub county `c`:

- `p99[h]` = the annualized frequency of the 99th-percentile US county (all ~3,232 counties, null counted as 0; sorted, index `floor(0.99 × (N − 1))`).
- If `afreq[c][h]` is `null` or `0`, or `p99[h]` is 0: indicator = **0** (FEMA rates the hazard as absent or not applicable).
- Otherwise: indicator = `min(100, 100 × afreq[c][h] / p99[h])`.

Meaning: "this county has X% as many of these events per year as a top-1% US county." Raw value: events per year. This keeps magnitude: the first version used a percentile rank, which gave Dallas a hurricane score of 49.5 for a frequency 1/26 of Miami's (see `docs/decisions.md`).

### 3b. Observed weather indicator

Annual average count of qualifying days over the scoring window (2016-2025), mapped linearly: `min(100, 100 × annual_average / cap)`. Missing days are excluded and the average is scaled to a full year.

| Indicator | A qualifying day | Cap (= 100) |
|---|---|---|
| `heavy_snow_days` | snowfall ≥ 5 cm (about 2 in) | 15 days/yr |
| `severe_cold_days` | min temperature ≤ -18 °C (0 °F) | 20 days/yr |
| `extreme_heat_days` | max temperature ≥ 35 °C (95 °F) | 60 days/yr |
| `heavy_rain_days` | precipitation ≥ 50 mm (about 2 in) | 4 days/yr |
| `high_wind_days` | max gust ≥ 90 km/h (about 56 mph) | 10 days/yr |

## 4. Hazard scores

Each hazard score is a weighted sum of its indicators (weights add to 1.0).

| Hazard | Indicators and weights |
|---|---|
| **winter** | FEMA `WNTW` 0.25, FEMA `ISTM` 0.15, FEMA `CWAV` 0.10, `heavy_snow_days` 0.25, `severe_cold_days` 0.25 |
| **heat** | FEMA `HWAV` 0.50, `extreme_heat_days` 0.50 |
| **flood** | FEMA flood = max(`IFLD`, `CFLD`) percentile 0.70, `heavy_rain_days` 0.30 |
| **hurricane** | FEMA `HRCN` 1.00 |
| **severe_storms** | FEMA `TRND` 0.30, FEMA `HAIL` 0.25, FEMA `SWND` 0.25, `high_wind_days` 0.20 |

Why flood uses `max`: inland and coastal flooding are different mechanisms, and a coastal hub should not have its flood exposure diluted by low inland flooding.

Why hurricane is FEMA-only: daily reanalysis cannot tell a hurricane day from any other windy, rainy day.

**HazardScore**: `hub_id`, `hazard`, `score` (0-100, rounded to 1 decimal only for display), `components: list[Component]`.

**Component**: `indicator`, `weight`, `indicator_score` (0-100), `contribution` (= weight × indicator_score), `raw_value`, `raw_unit` ("events/yr" or "days/yr"), `source`.

Rule: `sum(component.contribution) == score` (tested).

## 5. Overall score and ranking

**OverallScore**: `hub_id`, `score` = mean of the five hazard scores (equal weights, 0.2 each), `hazards: list[HazardScore]`, `rank` (1 = most exposed).

**Ranking**: list of `(rank, hub_id, score)` for one hazard or `overall`, optionally filtered by region.
- Sort by unrounded score descending; **tie-break by hub `id` alphabetically**.
- Equal unrounded scores share the same displayed score but keep distinct ranks in tie-break order; the table marks ties.

**Plausibility tests** (written before looking at real scores, run against the seed snapshot):
- Miami and Houston are the top 2 hubs for `hurricane`.
- Phoenix and Dallas are the top 2 hubs for `heat`.
- Minneapolis is in the top 3 for `winter`.
- Los Angeles is in the bottom 3 for `winter`.
- Denver's `hurricane` score is 0.

If one fails, first look for a bug or a data problem. A weight or cap may change only with a dated entry in `docs/decisions.md` explaining why, never just to make a test pass.

**Missing components**: if a whole indicator is unavailable for a hub (a source failed and there is no earlier snapshot), the hazard score is the weighted sum of the remaining indicators with weights re-normalized to 1.0, and the component is flagged `missing`. Answers then list it as a limitation and confidence cannot be `high`.

## 6. Statistics

**WeatherStat**: `hub_id`, `stat`, `period_start`, `period_end`, `value`, `unit`, `qualifying_days`, `days_with_data`, `missing_days`, `definition`.

| `stat` | Definition | `value` |
|---|---|---|
| `snowfall_days_pct` | days with snowfall ≥ 0.25 cm (0.1 in, the NWS "measurable snowfall" threshold) | % of days with data |
| `heavy_snow_days` | snowfall ≥ 5 cm | count |
| `extreme_heat_days` | max temp ≥ 35 °C | count |
| `severe_cold_days` | min temp ≤ -18 °C | count |
| `heavy_rain_days` | precipitation ≥ 50 mm | count |
| `high_wind_days` | max gust ≥ 90 km/h | count |
| `total_snowfall_cm` | sum of snowfall | cm |
| `total_precipitation_mm` | sum of precipitation | mm |

Period: one calendar year from 2016 to 2025 ("last year" = 2025). Percent = `100 × qualifying_days / days_with_data`; missing days are excluded from the denominator and reported.

## 7. Agent and conversation

**ToolCallRecord**: `call_id`, `tool`, `arguments`, `result` (the tool's JSON), `display_table` (rows built by code from the result), `sources`.

**AgentAnswer** (the strict JSON schema the LLM must return; all fields required, nullable where noted):

| Field | Type | Notes |
|---|---|---|
| `answer_type` | enum: `answer`, `clarification`, `refusal` | |
| `narrative` | str | explanation in words; must not introduce numbers absent from tool results |
| `assumptions` | list[str] | |
| `limitations` | list[str] | may be empty |
| `confidence` | object: `level` enum `low`/`medium`/`high`, `reason` str | |
| `clarifying_question` | str or null | set only when `answer_type` = `clarification` |

**ChatResponse** (what the API returns; built by code): `conversation_id`, `answer` (AgentAnswer), `tables` (display tables from this turn's tool calls, rendered by code), `data_sources` (deduplicated from this turn's tool calls, each with source name, period, retrieval date; filled by code, not the LLM), `tool_calls` (name and arguments, for transparency), `error` (null or a user-safe message).

**Conversation**: `id` (UUID4), `turns` (last 20 messages, including tool calls and results), `updated_at`. In memory only.

## 8. Eval case

**EvalCase** (in `evals/cases.yaml`): `id`, `category` (one of `example`, `ranking`, `explanation`, `comparison`, `statistic`, `follow_up`, `out_of_scope`, `adversarial`), `turns: list[str]`, and per final turn `expect`:
- `tools_called` (each with optional required arguments, for example `{tool: rank_hubs, args: {region: Midwest, hazard: winter}}`)
- `hubs_in_tables` (exact set or ordered list)
- `answer_type`
- `numbers_match_engine: true` (rendered table values equal a fresh engine call)
- `narrative_must_not_contain` (optional; for example invented hub names)

Applied to every case automatically: `narrative_numbers_grounded` (every number in the narrative appears, within display rounding, in that turn's tool results; years and rank ordinals from the question are allowed) and a recorded duration for latency reporting.
