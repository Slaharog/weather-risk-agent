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

## 2026-11-13 - FEMA indicator: percentile rank replaced by ratio to the national p99 county

- **What happened:** the blind plausibility tests passed, but reviewing the real scores showed inland hubs with large hurricane scores (Dallas, Phoenix, St. Louis about 49; Chicago 39). FEMA rates Dallas at 0.0115 hurricane events/yr versus Miami at 0.305 (about 26x). A percentile rank keeps only order: about 27% of counties have zero hurricane frequency, so any non-zero value jumps to the middle of the distribution. Flood and severe-storm scores were compressed the same way.
- **Chosen (user decision):** score = min(100, 100 x county frequency / frequency of the 99th-percentile US county). Linear like the weather-day indicators, still an absolute national yardstick. Hurricane now: Miami 99.9, Houston 60.1, Newark 35.0, Dallas 3.8.
- **Alternatives:** keep percentile rank (simple wording, misleading magnitudes); percentile among exposed counties only (Dallas 30.8, still loses magnitude).
- **Not a test-fitting change:** all five plausibility tests passed both before and after; the change fixes magnitude, which those tests do not measure.
- **Effect on overall ranking:** Houston 48.4, Dallas 46.0, Miami 41.4 lead; Dallas no longer gets an inflated hurricane component.

## 2026-11-13 - Eval results (feature 001)

- **gpt-6.1-sol (default): 20/20 twice in a row.** 0 table mismatches, 0 ungrounded narrative numbers; p50 about 6.5 s, p95 about 15 s; about 93k input / 4k output tokens for the whole set (44 model calls). Optional LLM judge (reported separately): clarity 4.9/5. Results: `evals/results/20261113T115806Z.json`, `20261113T120140Z.json`.
- **No prompt iteration was needed.** The first prompt passed. To check the evals are not simply too easy, the same set was run on the cheaper `gpt-6-luna`: 18/20 (`evals/results/20261113T120435Z.json`), so the checks do discriminate between models.
- **One eval fix, not a prompt fix:** Luna's earthquake refusal ("Earthquake exposure is not among the hazards this system scores") was correct but missed my substring list. I widened the accepted phrasings; both models then pass that case, so Luna is effectively 19/20.
- **Remaining Luna failure is real per the spec:** on an ambiguous "that one" it answered for both hubs instead of asking a clarifying question. Reasonable, but the spec (US5 scenario 2) asks for clarification. Sol asks.
- **Model choice stays gpt-6.1-sol:** Luna is faster at the median (4.6 s) but had one 65 s outlier (p95) and misses the clarification behavior. Evidence-based model choice is the interview answer to "why this model?".
- **Known limit of the evals:** 20 hand-written cases, single run each; substring checks for refusals can miss valid phrasings (as seen). A larger, paraphrased set is the first thing to grow.

## 2026-11-13 - Review findings and fixes (T059-T060)

Two independent review agents ran on the finished code: a security auditor and a code reviewer.

- **Security (1 confirmed, medium):** `/api/chat` had no rate limit, so a public URL could drain the OpenAI budget or tie up all threads. Fixed with an in-memory limiter (10 messages/min per client, 500/day overall) and a 16 KB body cap. Production notes kept as known limits: no auth (single-tenant demo), conversation ids act as bearer tokens, no CSP headers.
- **The eval checker was too lenient (2 high, 1 medium).** Grounding allowed a ±0.05 tolerance and sign flips (any small invented number near a 0 passed), it drew allowed numbers from the whole conversation instead of the current turn, and `numbers_match_engine` compared the tool code with itself. Rewritten: exact displayed values only, this turn only, tables checked against the engine's own API. Rerun: still 20/20 with gpt-6.1-sol, 0 ungrounded numbers. The earlier 20/20 results were real but weaker evidence than claimed.
- **Correctness (fixed, test-first):** a year with no data returned "0%" instead of an error, and days absent from the data were not counted as missing; the missing-data flag looked at every hazard instead of the ones shown; missing data lowered confidence but was not named in `limitations` as the data model requires (now added by code); failed answer attempts were saved to history; `clarifying_question` was not validated; two concurrent requests on one conversation could lose a turn (per-conversation lock); a snapshot/hub mismatch gave a raw KeyError (now a clear DataError).
- **Simplified:** the server reloads scores only after `wra refresh` writes a completion marker (it could previously reload mid-refresh); duplicated schema-cleaning branches merged.
- **Spec/contract aligned with the code:** `/api/health` returns `data_sources`; conversation history is "last 20 user turns with their tool calls".
- **Not changed:** `Engine.rank_of` recomputes rankings per call (16 hubs; negligible), kept for readability.

## 2026-11-13 - Railway deployment (step 1, no spec)

- **Build: Dockerfile, not Railpack.** `python:3.12-slim` plus the pinned uv binary (0.13.3), dependencies in their own layer (`uv sync --locked --no-dev --no-install-project`), then the code and the committed seed. Alternative: Railpack, which auto-detects `uv.lock` with zero config. Rejected because its build steps are implicit, so they are harder to explain and cannot be reproduced locally; the Dockerfile was built and run locally with Docker before the first deploy.
- **Config as code:** `railway.toml` sets the Dockerfile builder, the healthcheck (`/api/health`) and the restart policy. Secrets and environment values (`OPENAI_API_KEY`, `DATA_DIR`, `TRUSTED_IP_HEADER`) are Railway variables, never in the repo or the image (`.dockerignore` excludes `.env`).
- **Real client IPs for the rate limiter.** Railway's docs list `X-Real-IP` as the client-IP header and do not list `X-Forwarded-For`, which is the only header uvicorn's `forwarded_allow_ips` reads. Behind the proxy every request would otherwise share the proxy's IP, turning the per-client limit into one global limit. Chosen: a setting `TRUSTED_IP_HEADER` (unset locally, `X-Real-IP` on Railway); when set, the limiter keys on that header. Unset by default, because without a proxy in front a client could set the header itself to dodge the limit. Two smoke tests cover both cases. Alternative: `forwarded_allow_ips="*"`, rejected because it depends on a header Railway does not document.
- **Deploy route: GitHub repo connected in the Railway dashboard.** The Railway CLI was the first choice, but Windows Application Control blocks `railway.exe` on the development machine (the same block as `wra.exe`). The dashboard route also gives auto-deploy on every push to `main`.
- **Volume** mounted at `/data`, with `DATA_DIR=/data`. Nothing writes there yet except `wra refresh`; it exists for the alert feature's SQLite score history. Railway does not allow replicas with a volume, which matches the single-instance design (in-memory conversations and rate limits).
- **Local test quirk:** the development machine's antivirus (Avast Web/Mail Shield) re-signs TLS, so `uv sync` inside a local Docker build fails with `UnknownIssuer`. The local test used a scratch copy of the Dockerfile that trusts that root CA; the committed Dockerfile has no such workaround, because Railway's builders reach PyPI directly.
- **Deploy smoke check:** `python scripts/smoke_deploy.py <url>` checks health, an LLM-free ranking and one chat question.
- **Live verification (2026-11-13), https://weather-risk-agent-production.up.railway.app:** `scripts/smoke_deploy.py` passed (health 200; Midwest winter ranking Minneapolis 51.2, Detroit 28.5, Chicago 24.4, identical to local; one grounded chat answer). Rate limit: 10 chat requests returned 200 and the 11th returned 429; a further request with a spoofed `X-Real-IP` also returned 429, so Railway's edge replaces a client-supplied value. Not proven from one machine: that two different real clients get separate buckets (that needs a second network); the evidence is Railway's documented header plus the unit test.

## 2026-11-13 - Spec 002 (risk-change alert): clarifications and plan

- **Watched scores and threshold:** each hub's overall score and five hazard scores; an alert fires when the change is at least 2.0 points. Alternatives: overall only (a 5-point move in one hazard moves overall by only 1 point and would be missed), 5.0 points (too quiet for real data revisions).
- **A check is a refresh.** The scheduled check fetches into `DATA_DIR` exactly like `wra refresh`, so alerts, rankings and chat always describe the same data. Alternatives: compare in an isolated staging area (alerts could describe scores the chat does not show), recompute only (the schedule would rarely see anything new).
- **Demo = simulated previous scores.** Today's real scores are compared with a copy shifted for two hubs (Dallas heat 7.5 lower, Houston hurricane 5.0 higher), giving exactly 2 demo-labeled alerts through the real detection, recording, delivery and listing path. Nothing is written to the real score history, so the next real check is unaffected. Alternatives: perturbed raw data (more code, harder to isolate), test fixture only (nothing to show live). The first draft shifted Miami hurricane upward, which would have put the simulated value at 104.9, off the 0-100 scale; it was caught while checking the numbers against the engine and changed to Houston.
- **Trigger protection:** `POST /api/alerts/check|demo` need an operator bearer token from env (constant-time compare), and are disabled when none is set; the CLI needs no token; `GET /api/alerts` is public and never returns the webhook URL. Alternatives: open demo endpoint (anyone could spam the webhook), CLI only (no live demo, because `railway.exe` is blocked here).
- **Scheduler:** an asyncio task in the FastAPI lifespan polls every 10 minutes and runs a due check in a worker thread; "due" is computed from SQLite, so redeploys neither skip nor repeat checks. Off by default (`ALERT_INTERVAL_HOURS=0`) so local runs and evals never fetch live data by surprise. Alternative: APScheduler (a dependency; its schedule restarts on each redeploy without a job store).
- **Storage:** stdlib `sqlite3`, raw SQL, 3 tables in `DATA_DIR/alerts.sqlite`. Alternatives: SQLModel (a dependency for 3 tables), JSON-lines files (needs a constitution justification).
- **Precision:** scores are rounded to one decimal, as displayed, before they are stored and compared, so an alert's numbers always match rankings and chat.
- **Webhook:** a generic JSON POST with a Slack-compatible `text` field, tested with webhook.site; 5 s timeout, 3 attempts; the URL is never logged or returned.
