# Decision log

Each entry records what was chosen, the alternatives considered, and why.

## 2026-11-12 - Process: spec-driven development with Spec Kit

- **Chosen:** Spec Kit (constitution, specify, clarify, plan, tasks, analyze, implement), with user approval gates before planning and before implementation.
- **Why:** makes the plan reviewable, keeps the AI on a written contract, and leaves a readable trail of reasoning for the submitted session log.

## 2026-11-12 - LLM provider: OpenAI

- **Chosen:** OpenAI, using Structured Outputs (strict `json_schema`) and function calling.
- **Alternatives:** Anthropic Claude (equally capable here), local Ollama (free, but weaker tool calling and hard to deploy).
- **Why:** an existing API key, and it fully covers the JSON schema and tool-calling requirements. The provider sits behind one module, so swapping it is a small change.

## 2026-11-12 - Deployment: Railway

- **Chosen:** Railway, one long-lived FastAPI service with a volume for SQLite.
- **Alternatives:** Vercel (serverless), Render free tier, local only.
- **Why:** the app is stateful (SQLite cache, score history) and runs a background scheduler for alerts. Serverless has no persistent disk and no background process, so it would need a hosted database and a cron trigger: more moving parts for a 24-hour task. Railway gives dev/prod parity. Render's free tier sleeps when idle, which is risky for a live demo.

## 2026-11-12 - Scope extras

- **Chosen:** risk-change alert (bonus) and browser voice input (bonus), both kept small. Core requirements come first.

## 2026-11-13 - Constitution v1.1.0 (after grilling)

- **Code renders the numbers.** The LLM writes the narrative only. Alternative: trust the prompt and catch drift in evals. Rejected because a garbled number in an investment decision is the worst failure for this product.
- **Decomposable scores.** Weighted sum of per-hazard components, returned by the tools. This makes "why is Dallas high?" a deterministic answer. ML or LLM-assigned scores were rejected as opaque.
- **No agent framework.** One agent with a few read-only tools needs a loop of roughly 60-100 lines, not LangGraph or the Agents SDK. A framework would be justified for multi-agent handoffs, durable workflows, or human-approval steps.
- **Evals.** Deterministic checks (tool choice, hubs, number match, refusals) are the primary pass rate. An optional LLM judge for explanation quality is reported separately.
- **Uncertainty in the schema.** Required fields `data_sources`, `assumptions`, `limitations`, `confidence` make Principle III structural rather than a prompt hope.
- **Seed snapshot of real data.** Real API responses for the historical window are committed, so clones, evals, and the live demo work without the network and give reproducible numbers. A `refresh` command and the alert job use the live APIs. Alternative: empty cache filled on first use, simpler but exposed to API outages and data revisions.
- **TDD scope.** Strict test-first for scoring, statistics, and normalization; smoke tests for routes, UI, and the scheduler.

## 2026-11-13 - Spec 001 clarifications

- **16 hubs** at real logistics cities (7 Midwest, 5 South, 3 West, 1 Northeast). Alternatives: 8 hubs (rankings too thin) or 25+ (more data to verify, no demo gain). The company supplied no list, so this is a stated assumption.
- **Absolute scoring.** Each hazard is scored against a fixed national yardstick, so a hub's score does not move when the hub list changes, and a score change (for the later alert feature) means the data changed. Alternative: min-max relative to our hubs, simpler but unstable and it exaggerates small differences. Cost: the thresholds are our judgment calls and must be documented.
- **Five hazards:** winter, hurricane/tropical wind, flood, extreme heat, severe storms. Alternative: only the three named in the brief, rejected because "why is Dallas high?" cannot be answered truthfully without heat and severe storms.

## 2026-11-13 - Spec 001: scoring visible without the LLM (FR-029)

- **Chosen:** a direct API endpoint and a CLI command show rankings and breakdowns with no LLM involved; the agent tools call the same functions.
- **Why:** proves the deterministic engine stands alone (assignment: "not only LLM output") and gives a demo path if the LLM is unavailable.

## 2026-11-13 - Plan 001: data sources and scoring

- **Sources:** Open-Meteo ERA5 daily history (keyless; non-commercial terms) and FEMA National Risk Index Dec 2025 county event frequencies via FEMA's public ArcGIS service (keyless). Rejected NOAA station data (token, gaps) and FEMA risk scores (they mix in property value and population, so they measure county loss, not hub exposure).
- **Scoring:** each hazard is a weighted sum of FEMA national frequency percentiles and observed-day indicators on fixed caps; overall = mean of 5 hazards. Caps and weights are documented judgment calls.
- **Model:** OpenAI Responses API, default `gpt-6.1-sol` (OpenAI's "balance intelligence and cost" pick), configurable; reasoning effort instead of temperature.
- **Storage:** JSON files only for 001; SQLite deferred to the alert spec.

## 2026-11-13 - Scoring grilling (plan 001)

- **Overall = equal average of 5 hazards.** Alternative: 0.5 x mean + 0.5 x worst hazard, to reward single extreme hazards (Miami hurricanes). Rejected for simplicity; per-hazard rankings already surface single-hazard hotspots.
- **Source mix as planned.** Each hazard leans on the source that measures it best: hurricane FEMA only (reanalysis cannot identify hurricanes), storms 80% and floods 70% FEMA (the 25 km grid smooths gusts and local downpours), winter and heat 50/50 (the grid measures snow, cold and heat well). Alternatives: FEMA only (weather API would not affect rankings), weather-heavier (weakest exactly where it would weigh most).
- **Fixed, documented caps.** Alternatives: caps from our 16 hubs (makes scores relative, reversing the absolute-scoring decision), caps from a national grid of ~100 points (most defensible, too costly for 24h).
- **10-year window, 2016-2025.** Alternatives: 30-year climate normal (more stable, may understate recent trends), 5 years (too noisy).
- **Snowfall day >= 0.25 cm (0.1 in)**, the NWS "measurable snowfall" threshold. Alternatives: > 0 (inflated by trace amounts in model data), >= 1 cm (no standard behind it).
- **Plausibility tests** written before seeing real scores. Rule: a failure triggers a bug/data investigation first; any weight or cap change needs a dated entry here.
- **Step 3 milestone:** CLI plus JSON API, no separate rankings web page.

## 2026-11-13 - speckit-analyze remediation

- Added eval check `narrative_numbers_grounded` (the LLM narrative may only use numbers present in tool results) and latency reporting (SC-008).
- Spec: a non-hub city now gets "hubs in the same region" instead of "the nearest hub" (no geocoding, so "nearest" would be an LLM guess).
- Refresh recomputes and the server reloads when the manifest changes; code lowers confidence when data is missing.
- Constitution v1.1.1 (PATCH): eval sampling wording covers reasoning models.
