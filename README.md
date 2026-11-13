# Weather Risk Intelligence Agent

An AI agent that helps logistics analysts decide which US distribution hubs are most exposed to weather disruption, and why.

- **Deterministic engine.** Plain Python scores 16 hubs on 5 hazards from two public data sources. No LLM touches a number.
- **Conversational agent.** An OpenAI model answers questions in plain language. It uses five read-only tools that call the engine, and returns a strict JSON answer.
- **One FastAPI service** serves the chat page, the agent API, and LLM-free ranking endpoints.
- **Evals.** A 20-case eval set runs with one command. The latest result is 20/20 on `gpt-6.1-sol` (details in [Evaluation](#evaluation)).

```
Which hubs in the Midwest are most exposed to winter disruption?   -> rank_hubs(winter, Midwest)
Compare Miami and Houston in terms of hurricane and flood exposure. -> compare_hubs([miami, houston], [hurricane, flood])
What percentage of days in Denver last year had snowfall?          -> get_weather_stat(denver, snowfall_days_pct, 2025)
Why is the Dallas hub's weather disruption risk high?              -> get_hub_breakdown(dallas)
```

Design document: [`docs/architecture.md`](docs/architecture.md). Decision log with every trade-off: [`docs/decisions.md`](docs/decisions.md). Spec, plan and tasks: [`specs/001-core-risk-agent/`](specs/001-core-risk-agent/). AI session log: [`docs/session/`](docs/session/).

---

## Quick start

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/). An OpenAI API key is needed **only** for chat and evals; the scoring engine, CLI and ranking API work without it, and without network access.

```bash
uv sync
cp .env.example .env          # then set OPENAI_API_KEY in .env
uv run wra serve              # open http://localhost:8000
```

### Commands

| Command | What it does | Needs LLM |
|---|---|---|
| `uv run wra rank --hazard winter --region Midwest` | Ranking table | No |
| `uv run wra breakdown dallas` | Every component behind a hub's score | No |
| `uv run wra stat denver snowfall_days_pct --year 2025` | One weather statistic with its counts | No |
| `uv run wra serve` | API and chat page on port 8000 | For chat |
| `uv run wra eval [--model NAME] [--case ID] [--judge]` | Runs the eval set, writes `evals/results/*.json` | Yes |
| `uv run wra refresh [--source weather\|nri\|all]` | Fetches fresh data from the public APIs into `data/live/` | No |
| `uv run python -m pytest` | 133 unit and smoke tests (no network, no LLM) | No |

`python -m weather_risk <command>` is equivalent to `wra <command>`.

**Windows notes, from the development machine:**
- If Windows Application Control blocks the `wra.exe` or `pytest.exe` launchers, use `uv run python -m weather_risk ...` and `uv run python -m pytest`.
- If `uv` fails with `invalid peer certificate: UnknownIssuer`, a proxy or antivirus is re-signing TLS. Set `UV_SYSTEM_CERTS=1`. The app itself already uses the OS certificate store.

### HTTP API

| Endpoint | Purpose |
|---|---|
| `POST /api/chat` `{conversation_id, message}` | Ask the agent; returns narrative, tables, sources, assumptions, limitations, confidence |
| `GET /api/rankings?hazard=winter&region=Midwest` | LLM-free ranking |
| `GET /api/hubs/{hub_id}/breakdown` | LLM-free score breakdown |
| `GET /api/hubs`, `GET /api/health` | Hub list; data snapshot and model info |
| `GET /docs` | Interactive OpenAPI docs |

---

## How the scoring works

**Exposure, not loss.** A score says how often and how severely a hazard occurs at a hub's location, on a 0–100 scale. It does not include hub size, shipment volume, or existing protections, because no such data was provided.

Every score is a **weighted sum of indicators**. The engine keeps every component, so any score can be explained and recomputed by hand. Run `wra breakdown <hub>` to see one.

### Indicators (each 0–100)

1. **FEMA event frequency.** This is the hub county's expected events per year, from the FEMA National Risk Index, divided by the frequency of the **99th-percentile US county** (out of 3,232 counties) and capped at 100. "Not applicable" or zero gives 0.
   - Example: Miami averages 0.305 hurricane events a year, the national 99th-percentile value, so it scores 99.9. Dallas averages 0.0115 a year, so it scores 3.8.
2. **Observed weather days.** These are qualifying days per year at the hub over 2016–2025, from Open-Meteo, mapped linearly onto a fixed cap:

| Indicator | Qualifying day | Days/yr that score 100 |
|---|---|---|
| heavy snow | snowfall ≥ 5 cm (about 2 in) | 15 |
| severe cold | minimum ≤ −18 °C (0 °F) | 20 |
| extreme heat | maximum ≥ 35 °C (95 °F) | 60 |
| heavy rain | precipitation ≥ 50 mm (about 2 in) | 4 |
| high wind | gust ≥ 90 km/h (about 56 mph) | 10 |

### Hazard weights

| Hazard | Indicators and weights |
|---|---|
| winter | FEMA winter weather 0.25, ice storm 0.15, cold wave 0.10, heavy snow days 0.25, severe cold days 0.25 |
| heat | FEMA heat wave 0.50, extreme heat days 0.50 |
| flood | FEMA flooding, worse of inland and coastal, 0.70; heavy rain days 0.30 |
| hurricane | FEMA hurricane 1.00 |
| severe storms | FEMA tornado 0.30, hail 0.25, strong wind 0.25, high wind days 0.20 |

**Overall** is the average of the five hazards. **Ranking** sorts by the unrounded score, with ties broken alphabetically by hub id.

Each hazard leans on the source that measures it best:
- Hurricane uses FEMA only, because daily weather data cannot tell a hurricane from any other storm.
- Storms and floods lean on FEMA, because a 25 km weather grid smooths out local gusts and downpours.

The weights and caps are judgment calls. They are documented here and in [`docs/decisions.md`](docs/decisions.md).

**Weather statistics** answer factual questions such as "percentage of days with snowfall" for one hub and one calendar year from 2016 to 2025. "Last year" means 2025. A snowfall day has at least 0.25 cm (0.1 in), the US National Weather Service "measurable snowfall" threshold. Days with missing data are excluded from the denominator and reported.

**Sanity check.** Five plausibility tests, written before looking at the real scores, check the engine against well-known US climate. For example, Miami and Houston must be the top 2 for hurricanes and Phoenix and Dallas the top 2 for heat. All five pass.

---

## Data

| Source | What | Period | Access |
|---|---|---|---|
| [FEMA National Risk Index](https://hazards.fema.gov/nri/) | County annualized event frequency for hurricane, inland and coastal flooding, winter weather, ice storm, cold wave, heat wave, tornado, hail, and strong wind | December 2025 release | Public ArcGIS service, no key |
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5 reanalysis) | Daily snowfall, precipitation, minimum and maximum temperature, and wind gusts at each hub | 2016-01-01 to 2025-12-31 | No key; CC BY 4.0; free tier is non-commercial |

**Snapshot.** All answers come from a snapshot of real API responses committed in `data/seed/`, retrieved on 2026-11-13, unless you run `wra refresh`. This keeps the app, tests, and evals reproducible, and keeps the demo working if an API is down.
- `wra refresh` writes to `data/live/`, one source at a time and atomically. A failed source keeps its previous data.
- The server reloads scores automatically after a refresh.
- `GET /api/health` and every answer show the source periods and retrieval dates.

---

## The agent

- **Loop.** It is a hand-written tool-calling loop in `src/weather_risk/agent/loop.py`, with no agent framework. It is capped at 6 model calls per message.
- **Five read-only tools on an allow-list:** `list_coverage`, `rank_hubs`, `get_hub_breakdown`, `compare_hubs`, and `get_weather_stat`.
  - Tool arguments are enum-typed (hub ids, hazards, regions, statistics), so the model cannot name a hub or hazard that doesn't exist.
  - Pydantic validates the arguments again before any tool runs.
- **Strict JSON answer.** The final answer uses OpenAI strict structured output, validated again with Pydantic, with one retry and then a clear error. The answer schema has **no numeric fields**. The required fields are `answer_type`, `narrative`, `assumptions`, `limitations`, `confidence`, and `clarifying_question`.
- **Numbers.** Tables and data sources in the response are built by code from tool results. The model writes only the narrative, and the evals check that every number in it appears in a tool result. If a tool reports missing data, code lowers the confidence from high to medium.
- **Follow-ups.** The server keeps conversations in memory: the last 20 user turns with their tool calls, at most 200 conversations, lost on restart. Ambiguous references get a clarifying question.
- **Budget protection.** `/api/chat` allows 10 messages per minute per client and 500 per day in total (`CHAT_PER_MINUTE`, `CHAT_PER_DAY`). Request bodies are capped at 16 KB. Also set a spend limit on the OpenAI project.
- **Model.** The default is `gpt-6.1-sol`, set with `OPENAI_MODEL`. All provider code lives in `agent/llm.py`, so the provider can be swapped by replacing that one module.

---

## Evaluation

`uv run wra eval` runs [`evals/cases.yaml`](evals/cases.yaml), 20 cases in 8 categories:
- the four example questions from the brief
- ranking, explanation (including a false premise), comparison, and statistics (including an unsupported year)
- multi-turn follow-ups (including an ambiguous one)
- out-of-scope questions
- adversarial prompts (prompt injection and data exfiltration)

**Deterministic checks**, applied to every case:
- The expected tools were called with the expected arguments.
- The tables show the expected hubs.
- The answer type is right.
- **Table numbers equal the engine's own API.** This is checked independently of the tool formatting code.
- **Every number in the narrative equals a value from this turn's tool results, exactly as displayed**, or comes from the user's own question. There is no rounding tolerance, so "51" for 51.2 fails.

An optional LLM judge (`--judge`) scores clarity and is reported separately, never in the pass rate.

| Run | Checker | Pass | Ungrounded numbers | p50 / p95 latency | Tokens (whole set) |
|---|---|---|---|---|---|
| **`gpt-6.1-sol` (default)** | **strict (current)** | **20/20** | **0** | 6.0 s / 13.8 s | 93k in / 4.1k out |
| `gpt-6.1-sol`, two earlier runs | lenient (first version) | 20/20, 20/20 | 0 | about 6.5 s / 15 s | 93k in / 4.1k out; judge clarity 4.9/5 |
| `gpt-6-luna` (cheaper) | lenient | 18/20 (19/20 after an eval phrasing fix) | 0 | 4.6 s / 64.8 s | 99k in / 3.7k out |

**The first checker was too lenient.** A code review found three problems:
- It allowed a ±0.05 tolerance, which accepts invented values near any zero.
- It drew allowed numbers from the whole conversation instead of the current turn.
- Its table check compared the tool code with itself, so it could not fail.

It was rewritten and the set was rerun; the default model still passes 20/20. The Luna run shows the checks tell models apart: it answered an ambiguous follow-up instead of asking for clarification. Result files are in `evals/results/`.

---

## Assumptions

- **Hubs.** The company supplied no hub list, so these are 16 assumed hubs at real logistics cities. The coordinates are city centers, and hazard data is county-level. See [`config/hubs.toml`](config/hubs.toml).
- **Regions** follow the US Census Bureau regions. "Midwest" covers 7 of our hubs.
- **Scores** measure exposure, not financial loss, and they come from history, not forecasts.
- **"Last year"** means 2025.
- **Use.** This is a single-tenant demo, with no authentication.

## Known limitations

- **ERA5 resolution.** ERA5 is a reanalysis on a grid of about 25 km. It smooths local extremes, especially thunderstorm gusts and very local snow and rain, which is why high-wind and heavy-rain days carry low weights.
- **County-level hazards.** FEMA data is per county, and a large county like Los Angeles or Maricopa mixes very different terrain.
- **Judgment calls.** The weights and caps are expert judgment. They are not calibrated against actual hub shutdowns, because no outage history was provided. With such data, I would fit the weights to past disruptions.
- **Open-Meteo license.** Its free tier is non-commercial. A production deployment would need its commercial plan.
- **Memory.** Conversations live in memory, so they disappear on restart and are not shared across server instances.
- **Eval size.** The eval set is small (20 hand-written cases, one run each). Substring checks for refusals can miss valid wordings; this happened once and was fixed in the eval, not the prompt.

## How AI was used

The whole project was built with Claude Code (Claude Opus 5.5) using spec-driven development (GitHub Spec Kit): a constitution, then a spec, clarifications, a plan with research, tasks, a consistency analysis, and test-first implementation. I approved every spec, plan, and scoring decision. The full session, including the plan and every decision, is in [`docs/session/`](docs/session/), and the reasoning is summarized in [`docs/decisions.md`](docs/decisions.md).

Examples of where the AI's first approach changed after review:
- The FEMA percentile-rank formula was replaced after real data showed it inflated rare hazards.
- A "nearest hub" requirement was dropped because it would have needed a geographic guess from the LLM.
- An eval check was widened after it rejected a correct refusal.
