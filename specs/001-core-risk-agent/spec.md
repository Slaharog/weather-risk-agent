# Feature Specification: Core Weather Risk Agent

**Feature Branch**: `001-core-risk-agent`

**Created**: 2026-11-13

**Status**: Approved (2026-11-13)

**Input**: User description: "Core weather risk agent: a fixed list of US distribution hubs with coordinates and regions; ingestion of public weather and hazard data with a committed seed snapshot of real API responses plus a refresh command; deterministic, decomposable per-hub risk scoring (weighted per-hazard components) and statistics such as percentage of snow days; an LLM agent (OpenAI, hand-written tool-calling loop, strict JSON schema final answer with data_sources, assumptions, limitations, confidence) that answers ranking, comparison, statistic, and "why" questions with conversational follow-ups; exposed through a FastAPI chat API used by a simple web chat page; plus a runnable eval set of 15-25 cases. Out of scope for this spec: scheduled risk-change alerts and voice input (separate specs)."

## User Scenarios & Testing *(mandatory)*

The primary user is a logistics **analyst** who must recommend which hubs get resilience investment this year. A secondary user is the **operator** (the developer or a reviewer) who runs the system, refreshes data, and checks its quality.

All analyst journeys happen in a chat conversation. Every answer has the same shape: a short narrative, a table of the relevant numbers, and an "about this answer" panel listing data sources and period, assumptions, limitations, and a confidence level.

### User Story 1 - Rank hubs by exposure (Priority: P1)

The analyst asks which hubs are most exposed to a hazard, optionally within a region, for example "Which hubs in the Midwest are most exposed to winter disruption?" The agent returns the matching hubs ranked by their score for that hazard, with each hub's score, the main contributing factors, and the reasoning.

**Why this priority**: ranking is the core decision the business wants support for: which hubs to invest in. On its own, this story is a usable product.

**Independent Test**: ask the Midwest winter question in the chat. Verify that only Midwest hubs appear, that they are ordered by winter score, and that the numbers equal the scoring output for those hubs.

**Acceptance Scenarios**:

1. **Given** the hub list and data snapshot are loaded, **When** the analyst asks "Which hubs in the Midwest are most exposed to winter disruption?", **Then** the answer lists only Midwest hubs, ranked highest to lowest by winter score, with the score and top contributing factors for each.
2. **Given** the same setup, **When** the analyst asks for the overall most at-risk hubs with no region or hazard, **Then** all hubs are ranked by overall score and the answer states which hazards drive the top hubs.
3. **Given** a region with no hubs, **When** the analyst asks about it, **Then** the agent says no hubs exist in that region and lists the regions that do.

---

### User Story 2 - Explain why a hub's risk is high (Priority: P1)

The analyst asks "Why is the Dallas hub's weather disruption risk high?" The agent shows the hub's overall score broken into per-hazard components, identifies the largest contributors, and explains each one with the underlying observations (for example, number of extreme heat days or the hazard rating for its location). It also shows how the hub compares with the other hubs.

**Why this priority**: an investment recommendation has to be defensible. The analyst must be able to explain any score to management, and this is what makes the ranking trustworthy.

**Independent Test**: ask the Dallas question. Verify that the components shown add up to the overall score, that the hazards named as main drivers are the largest components, and that the underlying values match the data.

**Acceptance Scenarios**:

1. **Given** the data is loaded, **When** the analyst asks why Dallas's risk is high, **Then** the answer shows every component of Dallas's overall score, the components sum to the overall score, and the narrative names the largest components as the drivers.
2. **Given** a hub whose risk is actually low relative to the others, **When** the analyst asks why it is high, **Then** the agent corrects the premise, states its actual position, and still shows the breakdown.

---

### User Story 3 - Compare hubs on chosen hazards (Priority: P2)

The analyst asks "Compare Miami and Houston in terms of hurricane and flood exposure." The agent returns a side-by-side comparison of the requested hazards for the requested hubs, states which hub is more exposed on each hazard, and explains the difference.

**Why this priority**: comparing shortlisted candidates is the next most common step after ranking.

**Independent Test**: ask the Miami/Houston question. Verify both hubs and both hazards appear, and that the "more exposed" verdict on each hazard matches the higher score.

**Acceptance Scenarios**:

1. **Given** the data is loaded, **When** the analyst compares Miami and Houston on hurricane and flood, **Then** the answer shows both hubs' scores for both hazards and a per-hazard verdict consistent with the scores.
2. **Given** the analyst names a city that is not a hub, **When** asking for a comparison, **Then** the agent says that city is not a hub, names the nearest hub if there is one, and does not invent data.

---

### User Story 4 - Ask a weather statistic (Priority: P2)

The analyst asks a factual question about observed weather at a hub, for example "What percentage of days in Denver last year had snowfall?" The agent returns the statistic, the exact period, the definition used (what counts as a snowfall day), and the count behind the percentage.

**Why this priority**: analysts check facts behind scores. It is also one of the four example questions in the brief.

**Independent Test**: ask the Denver question. Verify the percentage equals snowfall days divided by days with data in the stated period, and that the definition and period are stated.

**Acceptance Scenarios**:

1. **Given** the data covers last year, **When** the analyst asks for Denver's percentage of snowfall days last year, **Then** the answer gives the percentage, the number of snowfall days, the number of days with data, the calendar period, and the snowfall-day definition.
2. **Given** some days in the period have no data, **When** the statistic is computed, **Then** missing days are excluded from the denominator and the answer states how many days were missing.

---

### User Story 5 - Follow-up questions (Priority: P2)

Within one conversation, the analyst asks follow-ups that depend on earlier turns, such as "What about Chicago?", "And for heat instead?", or "Why is the first one so high?" The agent resolves the reference from the conversation and answers as if the full question had been asked.

**Why this priority**: required by the brief, and it is what makes the tool feel like an assistant instead of a form.

**Independent Test**: run a scripted 3-turn conversation (ranking, then "why is the top one high?", then "compare it with Chicago"). Verify each answer refers to the right hub and hazard.

**Acceptance Scenarios**:

1. **Given** the agent just ranked Midwest hubs for winter, **When** the analyst asks "Why is the first one so high?", **Then** the agent explains the top-ranked hub from the previous answer.
2. **Given** a follow-up is ambiguous (for example "what about that one?" after several hubs were named), **When** the agent cannot resolve it with confidence, **Then** it asks a short clarifying question instead of guessing.
3. **Given** the analyst starts a new conversation, **When** they ask a follow-up-style question, **Then** no context from earlier conversations is used.

---

### User Story 6 - Operator runs, refreshes, and evaluates the system (Priority: P3)

The operator starts the system from a fresh copy of the repository, uses it with no network access to the data providers, optionally refreshes data from the live public sources, and runs the eval set to get a quality report.

**Why this priority**: the brief requires a runnable eval set and run instructions, and the system must be demonstrable live. It delivers no analyst value on its own, so it ranks below the analyst stories.

**Independent Test**: on a fresh copy with data-provider access blocked, follow the README to start the system and ask one question; then run the evals and get a report.

**Acceptance Scenarios**:

1. **Given** a fresh copy and the required LLM credential, **When** the operator follows the run instructions, **Then** the chat works using the shipped data snapshot without contacting the data providers.
2. **Given** network access, **When** the operator runs the refresh command, **Then** data is fetched from the public sources, the snapshot is updated with a new retrieval date, and scores are recomputed.
3. **Given** the system is set up, **When** the operator runs the eval command, **Then** every case runs and a report shows the overall pass rate, the pass rate per category, and the reason for each failure.

---

### Edge Cases

- **Unknown hub or city**: the agent says it is not a hub, lists or suggests valid hubs, and never invents data.
- **Unsupported hazard** (for example earthquake, if not covered): the agent says the hazard is not covered and lists covered hazards.
- **Unsupported time period** (for example "in 1990" or "next month"): the agent states the period the data covers and declines or answers for the covered period, saying so.
- **Off-topic or unsafe requests** (unrelated questions, attempts to change the agent's instructions, requests to send data elsewhere): the agent declines briefly and restates what it can help with.
- **Data provider down during refresh**: refresh fails for that source with a clear message; the previous snapshot stays in use, and nothing is partially overwritten.
- **Missing data for a hub or hazard**: the score is computed from available components only if the rule for that case is defined (see FR-011); the answer lists the missing component and lowers confidence.
- **Ties in ranking**: tied hubs are shown with equal scores and a stable, documented tie-break order.
- **LLM output that fails validation twice**: the analyst sees a clear "could not produce a valid answer, please rephrase" message, never a malformed or partial answer.
- **Very long or empty input**: input over the limit is rejected with a message; empty input is ignored.
- **LLM service unavailable or credential missing**: the chat shows a clear error; the system does not crash.

## Requirements *(mandatory)*

### Functional Requirements

**Hubs**

- **FR-001**: The system MUST maintain one fixed, versioned list of hubs. Each hub has an identifier, display name, city, state, location coordinates, and region.
- **FR-002**: The hub list MUST contain these 16 hubs. Midwest: Chicago IL, Indianapolis IN, Columbus OH, Minneapolis MN, Kansas City MO, St. Louis MO, Detroit MI. South: Dallas TX, Houston TX, Miami FL, Atlanta GA, Memphis TN. West: Denver CO, Phoenix AZ, Los Angeles CA. Northeast: Newark NJ.
- **FR-003**: Regions MUST follow one documented definition, so "Midwest" and other region names map to a deterministic set of hubs.
- **FR-004**: The analyst MUST be able to ask which hubs, regions, and hazards the system covers.

**Data**

- **FR-005**: The system MUST obtain, for every hub, daily historical weather observations from a public source for a documented historical window, covering at least snowfall, precipitation, minimum and maximum temperature, and wind.
- **FR-006**: The system MUST obtain, for every hub location, public hazard ratings for hazards that daily weather cannot capture well (at minimum hurricane and flood).
- **FR-007**: The system MUST ship a snapshot of real responses from these sources, so that it runs and scores without contacting them.
- **FR-008**: The system MUST provide a refresh command that fetches current data from the public sources, records the retrieval date per source, and recomputes scores. A failed source MUST leave the previous snapshot for that source unchanged.
- **FR-009**: Every stored dataset MUST record its source and the period it covers, so answers can cite them.

**Scoring and statistics**

- **FR-010**: The system MUST compute, for every hub, a score from 0 to 100 for each covered hazard, using absolute scoring: each hazard is scored against a fixed, documented national yardstick (for example the national percentile of a public hazard rating, or an observed frequency mapped onto a fixed scale). A hub's score MUST NOT change when other hubs are added or removed. Rankings are produced by sorting these scores.
- **FR-011**: The system MUST compute an overall score per hub as a weighted sum of its hazard components. The weights and the rule for missing components MUST be documented in one place.
- **FR-012**: Scoring MUST be deterministic: the same data and configuration always produce identical scores and rankings, with a documented tie-break order.
- **FR-013**: For any hub, the system MUST provide the breakdown of the overall score into weighted components, plus the underlying observed values behind each component.
- **FR-014**: The system MUST compute weather statistics per hub and period, at minimum the percentage of days with snowfall, with the count of qualifying days, the count of days with data, and the count of missing days. Each statistic MUST use a documented definition (for example, what counts as a snowfall day).
- **FR-015**: The covered hazards MUST be exactly five: winter (snow, ice, extreme cold), hurricane and tropical wind, flood, extreme heat, and severe storms (tornado, hail, high wind). Each hazard MUST have a documented definition and data source.

**Agent**

- **FR-016**: The analyst MUST be able to ask, in natural language, ranking, explanation, comparison, statistic, and coverage questions, as in User Stories 1 to 4.
- **FR-017**: The agent MUST get every number from the system's scoring and statistics functions. Numbers shown to the analyst MUST be displayed from those results, not written by the language model.
- **FR-018**: Every answer MUST include data sources with periods, assumptions, limitations (possibly none), and a confidence level (low, medium, or high) with a one-line reason.
- **FR-019**: The agent MUST support follow-up questions within a conversation, using earlier turns of that conversation only, and MUST ask a clarifying question when a reference is ambiguous.
- **FR-020**: The agent MUST decline out-of-scope questions (unknown hubs, unsupported hazards or periods, off-topic requests) with a reason, and MUST NOT invent data.
- **FR-021**: The agent's structured output MUST be validated against a defined schema. On failure it retries once; on a second failure the analyst gets a clear error message.
- **FR-022**: The agent MUST only use a fixed set of read-only capabilities, MUST stop after a fixed maximum number of steps per question, and MUST reject input longer than a documented limit.

**Interface**

- **FR-023**: The system MUST expose the agent through a documented API that accepts a conversation identifier and a message and returns the structured answer.
- **FR-029**: Scores, rankings, and breakdowns MUST be viewable without the language model, through a direct API endpoint (for example, all hubs ranked by a chosen hazard) and a command-line command that prints the ranking table. The agent's capabilities MUST use the same scoring functions, so both paths always show identical numbers.
- **FR-024**: The system MUST provide a web chat page that uses that API, shows the narrative, the numbers table, and the "about this answer" panel, and lets the analyst start a new conversation.

**Evaluation and documentation**

- **FR-025**: The system MUST include an eval set of 15 to 25 cases covering: the four example questions from the brief, rankings, explanations, comparisons, statistics, multi-turn follow-ups, and out-of-scope or adversarial questions.
- **FR-026**: A single command MUST run the eval set and report the overall pass rate, the pass rate per category, and the reason for each failure.
- **FR-027**: Primary eval checks MUST be deterministic: expected capabilities used, expected hubs and hazards in the answer, displayed numbers equal to the scoring output, and refusals where expected. An optional quality judgment of the explanation MAY be reported separately.
- **FR-028**: The README MUST document how to run, refresh, and evaluate the system, the scoring definition and weights, statistic definitions, data sources and periods, assumptions, and known limitations.

### Key Entities

- **Hub**: a distribution hub. Identifier, name, city, state, coordinates, region.
- **Region**: a named group of states (for example Midwest). Maps deterministically to hubs.
- **Hazard**: a type of weather disruption the system scores (for example winter). Has a definition, its data sources, and its weight in the overall score.
- **Observation dataset**: daily weather values for one hub over a period. Records source, period, and retrieval date.
- **Hazard rating**: a public rating of a hazard for a hub's location. Records source and retrieval date.
- **Hazard score**: one hub's 0 to 100 score for one hazard, with the observed values it came from.
- **Overall score**: one hub's weighted sum of hazard scores, with its component breakdown and rank.
- **Statistic**: a computed value for a hub and period (for example percentage of snowfall days), with its definition and counts.
- **Conversation**: an ordered set of analyst messages and agent answers, identified so follow-ups use it.
- **Answer**: narrative, numbers table, data sources, assumptions, limitations, confidence.
- **Eval case**: a question or short conversation, its category, and its expected outcomes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All four example questions from the brief are answered correctly according to their eval cases.
- **SC-002**: At least 90% of eval cases pass the primary (deterministic) checks.
- **SC-003**: In 100% of eval cases, every number shown to the analyst equals the system's computed value.
- **SC-004**: 100% of out-of-scope and adversarial eval cases are declined or correctly limited, with no invented data.
- **SC-005**: Asking the same question twice on the same data gives identical scores and rankings 100% of the time.
- **SC-006**: 100% of answers include data sources with periods, assumptions, limitations, and a confidence level.
- **SC-007**: An operator with the required LLM credential goes from a fresh copy to a first answer in under 10 minutes by following the README, without contacting the data providers.
- **SC-008**: 95% of single questions are answered within 30 seconds.

## Assumptions

- The company supplied no hub list, so the hub list is defined by us, at real US cities, and documented as an assumption.
- The fixed thresholds that turn observed frequencies into 0 to 100 scores are our own judgment calls. They are documented with the scoring definition and listed as an assumption in answers that depend on them.
- "Midwest" and other regions follow the US Census Bureau region definitions.
- "Last year" means the most recent complete calendar year (2025, as of this spec).
- Scores measure **exposure** to weather disruption (how often and how severely a hazard occurs at the location). They do not model financial loss, hub size, shipment volume, or existing protections, because no such data was provided.
- Scores are based on historical climate and public hazard ratings, not on forecasts. Short-term forecasts are out of scope for this spec.
- A snowfall day is a day with measurable snowfall greater than zero as reported by the source. The exact threshold is documented with the statistic.
- Flood and hurricane exposure rely mainly on public hazard ratings, because daily weather data alone cannot show flooding or hurricane landfall reliably.
- This is a single-tenant demo for analysts. No user accounts or authentication are in scope, and conversations do not need to persist across restarts.
- English only, US hubs only.
- Out of scope for this spec: scheduled risk-change alerts and voice input (separate specs), forecasts, financial loss modeling, and editing the hub list through the chat.
- Dependencies: public weather and hazard data sources, and an external LLM service with a valid credential.
