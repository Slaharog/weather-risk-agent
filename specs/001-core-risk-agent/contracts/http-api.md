# Contract: HTTP API

Base path `/api`. JSON in and out. FastAPI also publishes the OpenAPI document at `/openapi.json` and interactive docs at `/docs`.

## POST /api/chat

Ask the agent. Creates a conversation when `conversation_id` is null.

Request:

```json
{ "conversation_id": null, "message": "Which hubs in the Midwest are most exposed to winter disruption?" }
```

- `message`: 1 to 1,000 characters after trimming. Otherwise `422`.
- `conversation_id`: UUID returned by an earlier call, or null. An unknown id starts a new conversation (the response carries the new id).

Response `200` (`ChatResponse`, see data-model §7):

```json
{
  "conversation_id": "6f1c…",
  "answer": {
    "answer_type": "answer",
    "narrative": "Minneapolis is the most exposed Midwest hub, driven mainly by severe cold days and FEMA winter-weather frequency…",
    "assumptions": ["Scores measure exposure, not financial loss."],
    "limitations": [],
    "confidence": { "level": "high", "reason": "Complete data for all Midwest hubs." },
    "clarifying_question": null
  },
  "tables": [
    { "title": "Midwest hubs ranked by winter score", "columns": ["Rank", "Hub", "Winter score", "Top driver"], "rows": [[1, "Minneapolis, MN", 71.3, "severe_cold_days"]] }
  ],
  "data_sources": [
    { "name": "FEMA National Risk Index", "period": "December 2025 release", "retrieved_at": "2026-11-13" },
    { "name": "Open-Meteo Historical Weather API (ERA5)", "period": "2016-01-01 to 2025-12-31", "retrieved_at": "2026-11-13" }
  ],
  "tool_calls": [ { "tool": "rank_hubs", "arguments": { "hazard": "winter", "region": "Midwest", "limit": null } } ],
  "error": null
}
```

(Numbers in this example are illustrative only.)

Errors: the response is still `200` with `answer` null and `error` set to a user-safe message when the LLM fails validation twice, the step limit is hit, or the LLM service is unavailable. `503` only if the service is misconfigured (no API key).

## GET /api/hubs

All hubs: `[{ "id", "name", "region", "lat", "lon", "county_fips" }]`.

## GET /api/rankings?hazard={hazard}&region={region}

LLM-free ranking (FR-029). `hazard`: `overall` (default), `winter`, `heat`, `flood`, `hurricane`, `severe_storms`. `region`: optional, one of the four regions. Unknown values give `422`.

Response: `{ "hazard", "region", "rankings": [ { "rank", "hub_id", "name", "score", "tied": false } ], "data_sources": [...] }`.

## GET /api/hubs/{hub_id}/breakdown

LLM-free score breakdown (FR-013, FR-029): the overall score, each hazard score, and each hazard's components (indicator, weight, indicator score, contribution, raw value, unit, source). Unknown hub gives `404`.

## GET /api/health

`{ "status": "ok", "data_snapshot": { "weather_retrieved_at", "nri_version", "nri_retrieved_at" }, "model": "gpt-6.1-sol" }`.

## GET /

The chat page (static HTML and JavaScript). It calls only `POST /api/chat`.
