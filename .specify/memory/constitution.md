<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0 (MINOR: materially expanded guidance after a grilling round)
Modified principles (no renames):
  I. Code renders all user-visible numbers; scores must be decomposable
  III. Final-answer schema requires data_sources, assumptions, limitations, confidence
  IV. TDD scope defined; deterministic eval checks primary, LLM judge separate
  V. Hand-written agent loop named explicitly, with when a framework becomes justified
  VI. Committed seed snapshot of real API data, plus live refresh
Added sections: none
Removed sections: none
Templates checked: plan-template.md, spec-template.md, tasks-template.md read this file at
  run time; none changed
Follow-up TODOs: none
-->

# Weather Risk Intelligence Agent Constitution

## Core Principles

### I. Deterministic Scoring, LLM Explains (NON-NEGOTIABLE)

- Every risk score, ranking, comparison, and statistic MUST be computed by plain Python
  functions from data. The LLM MUST NOT produce, adjust, or round a number on its own.
- The LLM's job is limited to: understanding the question, choosing tools and arguments,
  and explaining the tool results in words.
- Every number in an answer MUST trace back to a tool result in the same turn.
- Numbers shown to the user (scores, rankings, percentages) MUST be rendered by code from
  tool results. The LLM writes the narrative and refers to those numbers; it does not copy
  or restate them as its own output.
- Every score MUST be decomposable: a transparent weighted sum of per-hazard components
  (for example `total = sum(weight_h * normalized_h)`), and tools MUST return each component
  so "why" questions are answered from the breakdown. Opaque scoring (ML models,
  LLM-assigned scores) is not allowed.
- The scoring logic (factors, weights, normalization) MUST be documented in one place and
  be readable without running the code.

Rationale: the assignment requires deterministic logic, and analysts deciding on investments
need numbers they can reproduce and audit. An LLM is the wrong tool for arithmetic.

### II. Enforced Structured Contracts

- All LLM output consumed by code MUST conform to a JSON schema generated from Pydantic
  models and enforced with the provider's strict structured-output mode.
- Tool arguments proposed by the LLM MUST be validated against their schema before any
  tool runs.
- On a schema violation the system MUST retry at most once, then return a clear error.
  It MUST NOT pass unvalidated output on.
- All LLM calls MUST go through one provider module, so the provider can be swapped
  without touching the rest of the code.

Rationale: the assignment requires a JSON schema contract between the LLM and code, and
strict validation is what makes LLM behavior safe to build on.

### III. Grounded and Honest Answers

- Answers MUST name the data source and the time period used.
- Answers MUST state assumptions, data gaps, and uncertainty when they affect the result.
- The final-answer JSON schema MUST require these fields: `data_sources` (source and
  period), `assumptions` (list), `limitations` (list, may be empty), and `confidence`
  (`low`, `medium`, or `high`, with a one-line reason). The chat UI shows them under every
  answer.
- Questions outside scope (unknown hubs, unsupported hazards, missing data) MUST get an
  explicit "cannot answer, because..." response, never an invented answer.
- The README and design doc MUST list the assumptions, the scoring definition, and known
  limits.

Rationale: the assignment asks to communicate assumptions, uncertainty, and scoping
clearly. A wrong answer delivered with confidence is worse than a stated limit.

### IV. Test-First and Measured by Evals

- Scoring, statistics, and data-normalization code MUST be developed test-first
  (red, green, refactor): write a failing test, then the simplest code that passes it.
- API routes, the chat page, and the scheduler need smoke tests only. Agent behavior is
  covered by the evals.
- The project MUST include an eval set of 15 to 25 cases that covers the example questions,
  follow-ups, comparisons, and out-of-scope questions, plus one command that runs it and
  prints a score.
- Primary eval checks MUST be deterministic: the expected tools were called with the
  expected hubs, rendered numbers match the scoring output, and out-of-scope questions are
  refused.
- An LLM judge MAY score explanation quality against a rubric, but its result MUST be
  reported separately and never mixed into the primary pass rate.
- Evals run each case once, at low temperature, against the cached data.
- No work is called done without running the tests and evals and showing their output.

Rationale: the assignment requires an eval set, and Moveo values evals. Tests turn
"it seems to work" into evidence.

### V. Narrow Scope, Explainable Code

- Build the smallest system that meets the requirements. Core requirements come before any
  bonus.
- No framework or abstraction is added unless it removes more complexity than it adds.
  The agent is a hand-written tool-calling loop with a hard step limit, not an agent
  framework (LangChain/LangGraph, OpenAI Agents SDK, CrewAI, PydanticAI). A framework becomes
  justified only for multi-agent handoffs, durable long-running workflows, or human-approval
  steps, none of which are in scope.
- The author MUST be able to explain every file and every line in the interview. Code that
  cannot be explained is simplified or removed.

Rationale: the assignment says a narrow scope done well beats a broad scope done shallowly,
and the follow-up interview tests understanding of the submitted code.

### VI. Reproducible Public Data

- Weather and hazard data MUST come from public APIs or public datasets, preferring sources
  that need no API key.
- Raw responses MUST be cached locally, so scores can be recomputed without the network and
  the live demo does not depend on a third-party API being up.
- A seed snapshot of real API responses for the historical window MUST be committed (for
  example under `data/seed/`), so a fresh clone runs the app and the evals with no network.
  A `refresh` command and the scheduled alert job fetch live data from the real APIs. The
  README states which answers come from the snapshot and when it was fetched.
- The hub list (names, coordinates, regions) MUST live in one versioned config file.
- The same inputs MUST always produce the same scores.

Rationale: reproducibility makes scores auditable and the live demo reliable.

### VII. Safe by Default

- Secrets MUST come from environment variables and MUST NOT be committed.
- Agent tools MUST be read-only, except the alert job's own score store.
- User input MUST be length-limited and treated as data. Tool calls MUST be restricted to a
  fixed allow-list, so prompt injection cannot reach new capabilities.
- Alert destinations (webhook URLs) MUST come from config, never from chat input.

Rationale: an FDE ships to client environments where these failures are costly. The
defaults matter more than the features.

## Technology and Delivery Constraints

- Language: Python 3.11 or later, managed with `uv`.
- API: FastAPI. The same process serves the chat page and runs the scheduled alert job.
- LLM: OpenAI through the official Python SDK, with strict structured outputs and function
  calling. The exact model is chosen during planning from current documentation.
- Storage: SQLite for the data cache and score history, unless a plan justifies otherwise.
- Chat UI: one static page served by FastAPI. Voice input uses the browser Web Speech API.
- Tests: `pytest`. Evals: a script run with a single documented command.
- Deployment: Railway, as one long-lived service with a volume for SQLite. The app MUST run
  locally first; deployment is the last step and MUST NOT block core work.
- Deadline: delivery within 24 hours of 2026-11-12. Scope decisions favor finishing.

## Development Workflow

- Spec-driven development with Spec Kit: constitution, specify, clarify, plan, tasks,
  analyze, implement. Each spec covers one feature and stays small.
- The user approves each spec before planning, and the plan and tasks before
  implementation. Specs and plans are stress-tested (grilled) before approval.
- Commit after each completed task, with a clear message. The history is part of the
  deliverable.
- Decisions, alternatives considered, and trade-offs are recorded in `docs/decisions.md`
  as they happen.
- Deliverables: source code with a README (how to run, assumptions, limits), a short design
  document (architecture, repository structure, data storage choice), the eval set and its
  results, and the full AI session log.
- Before claiming any work is complete, run the relevant tests or evals and show the output.

## Governance

- This constitution overrides other practices in this repository. Plans MUST include a
  Constitution Check, and any violation MUST be justified in the plan's complexity table.
- Amendments require the user's approval, an updated Sync Impact Report, and a version bump:
  MAJOR for removing or redefining a principle, MINOR for adding a principle or section or
  materially expanding guidance, PATCH for wording fixes.
- Reviews (`code-reviewer`, `reality-checker`, `speckit-analyze`) check compliance with these
  principles. Runtime guidance for the assistant lives in `CLAUDE.md`.

**Version**: 1.1.0 | **Ratified**: 2026-11-12 | **Last Amended**: 2026-11-13
