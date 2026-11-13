# Contract: Agent tools and the LLM output schema

The agent may call **only** these five read-only tools (allow-list, Principle VII). Each is an OpenAI function tool with `"strict": true`: every parameter is listed in `required`, optional ones are typed as a union with `null`, and `additionalProperties` is `false`. Arguments are validated again with Pydantic before the tool runs; invalid arguments return a structured error to the model instead of raising.

Each tool returns JSON with `data` (the deterministic result), `sources` (name, period, retrieval date), and `notes` (data-quality flags such as missing days or not-applicable hazards). Code builds the display table from `data`; the LLM never formats numbers for display.

Enums used below:
- `Hazard`: `winter`, `heat`, `flood`, `hurricane`, `severe_storms`
- `HazardOrOverall`: `Hazard` plus `overall`
- `Region`: `Midwest`, `South`, `West`, `Northeast`
- `HubId`: the 16 hub ids from data-model §1
- `StatName`: the stats in data-model §6

## list_coverage()

What the system covers: hubs (id, name, region), regions, hazards with one-line definitions, the data period, and the snapshot dates. Used for "which hubs do you have?" and to recover from unknown names.

Parameters: none.

## rank_hubs(hazard, region, limit)

| Param | Type | Notes |
|---|---|---|
| `hazard` | `HazardOrOverall` | |
| `region` | `Region` or null | null = all hubs |
| `limit` | integer 1-16 or null | null = all matching hubs |

Data: ordered `[{rank, hub_id, name, score, tied, top_drivers: [{indicator, contribution}] (top 2)}]`.

## get_hub_breakdown(hub_id)

| Param | Type |
|---|---|
| `hub_id` | `HubId` |

Data: the overall score and rank among all hubs, plus every hazard score with its rank and full components (data-model §4). Used for "why" questions.

## compare_hubs(hub_ids, hazards)

| Param | Type | Notes |
|---|---|---|
| `hub_ids` | list of `HubId`, 2-6 items, unique | |
| `hazards` | list of `HazardOrOverall`, 1-6 items, unique | |

Data: a matrix of hub × hazard scores with components, plus per hazard the `most_exposed` hub id (the higher score; ties are reported as a tie).

## get_weather_stat(hub_id, stat, year)

| Param | Type | Notes |
|---|---|---|
| `hub_id` | `HubId` | |
| `stat` | `StatName` | |
| `year` | integer 2016-2025 | "last year" = 2025, resolved by the model per the system prompt |

Data: `WeatherStat` (data-model §6) with value, counts, period, and definition.

## Final answer schema (`text.format`, strict)

`AgentAnswer` from data-model §7, sent as `{"type": "json_schema", "name": "agent_answer", "strict": true, "schema": …}` generated from the Pydantic model.

## Loop rules

- At most **6 model calls per user message** (tool rounds plus the final answer). Exceeding it returns a user-safe error.
- If the final output fails Pydantic validation: **one retry**, sending the validation error back to the model. A second failure returns a user-safe error (FR-021).
- Tool results are added to the conversation as tool outputs. User text is never interpreted as instructions to the code; it only reaches the model as a user message.
- Hub names in user text ("Dallas", "the Big D") are resolved by the model to `HubId` values via the enum. A city that is not a hub cannot be expressed in the enum, so the model must use `list_coverage` and say so.
