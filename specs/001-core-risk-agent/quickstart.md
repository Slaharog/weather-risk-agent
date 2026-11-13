# Quickstart and validation: Core Weather Risk Agent

This is the run-and-verify guide for feature 001. The README will carry the same steps for reviewers.

## Prerequisites

- Python 3.12 and `uv`
- An OpenAI API key (only for chat and evals; the scoring commands work without it)

## Setup

```powershell
uv sync
copy .env.example .env      # then set OPENAI_API_KEY in .env
```

## Validation scenarios

Run them in order. Each maps to spec requirements.

### V1. Deterministic engine works with no LLM and no network (FR-007, FR-012, FR-029, SC-005)

Disconnect from the network or skip the API key, then:

```powershell
uv run wra rank --hazard winter --region Midwest
uv run wra breakdown dallas
uv run wra stat denver snowfall_days_pct --year 2025
```

Expected:
- `rank` prints only the seven Midwest hubs, sorted by winter score.
- `breakdown` prints Dallas's five hazard scores and their components; the contributions add up to each hazard score.
- `stat` prints a percentage plus snowfall days, days with data, missing days, the 2025 period, and the 0.25 cm definition.
- Running each command twice prints identical output.

### V2. Unit tests (Principle IV)

```powershell
uv run pytest
```

Expected: all tests pass, including the percentile, indicator, scoring, ranking tie-break, and statistics tests.

### V3. API without the LLM (FR-023, FR-029)

```powershell
uv run wra serve
# in a second terminal:
curl "http://localhost:8000/api/rankings?hazard=winter&region=Midwest"
curl "http://localhost:8000/api/hubs/dallas/breakdown"
```

Expected: the same numbers as V1.

### V4. Chat (User Stories 1-5, FR-016 to FR-024)

Open `http://localhost:8000` and ask the four questions from the brief, then a follow-up:

1. "Which hubs in the Midwest are most exposed to winter disruption?"
2. "Why is the first one so high?" (follow-up)
3. "Compare Miami and Houston in terms of hurricane and flood exposure."
4. "What percentage of days in Denver last year had snowfall?"
5. "Why is the Dallas hub's weather disruption risk high?"
6. "What about Boston?" (not a hub: expect a clear "not a hub" answer)

Expected: every answer shows a narrative, a table whose numbers match V1 and V3, and the "about this answer" panel (sources with periods, assumptions, limitations, confidence).

### V5. Evals (FR-025 to FR-027, SC-001 to SC-004)

```powershell
uv run wra eval
```

Expected: a summary with the overall pass rate (target at least 90%), the pass rate per category, and the reason for each failure; a results file under `evals/results/`.

### V6. Refresh (FR-008)

```powershell
uv run wra refresh
```

Expected: both sources fetched, new retrieval dates shown by `GET /api/health`. With the network disabled, the command fails with a clear message and V1 still produces the previous numbers.

## Validation notes (T061, 2026-11-13)

Fresh `git clone` into an empty folder on the development machine (Windows 11, uv 0.13.3, `UV_SYSTEM_CERTS=1`):

- `uv sync`: 5 s (packages cached). No `.env` present.
- V1: `python -m weather_risk rank --hazard winter --region Midwest` printed the 7 Midwest hubs from the committed seed, no network to the data providers needed.
- V2: `python -m pytest`: 119 passed in 4.2 s.
- Total from clone to first ranking and green tests: 13 s (SC-007 target: under 10 minutes to first answer).
- V4/V5 (chat, evals) need `OPENAI_API_KEY`; verified separately in the working copy: the four brief questions answered in 5-8 s each, evals 20/20.
