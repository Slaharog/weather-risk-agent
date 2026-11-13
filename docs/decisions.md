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
