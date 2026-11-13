# Feature Specification: Risk-Change Alert

**Feature Branch**: `002-risk-change-alert` (work happens on `main`; no branch hook is configured)

**Created**: 2026-11-13

**Status**: Approved (2026-11-13)

**Input**: User description: "Risk-change alert (bonus feature). A scheduled job recomputes every hub's risk scores and records them; when a hub's score changes by more than a threshold compared with the last recorded score, the system fires an alert. Alerts go to a webhook URL that comes only from configuration/environment (never from chat), are always logged, and are listed at GET /api/alerts. A manual trigger (CLI command and/or endpoint) runs the check on demand for demos. Because real data changes rarely, there must be a way to demonstrate a change (e.g. a demo command or test fixture). Score history persists across restarts (planned: SQLite on the Railway volume at DATA_DIR). The scheduler runs inside the single FastAPI process. Change-detection logic is developed test-first. Core behavior (chat, rankings, evals) must not change."

## Clarifications

### Session 2026-11-13

- Q: How should the alert demo produce a score change? → A: Simulated previous scores: the demo runs the real detection code on today's real scores against a copy of them shifted by a fixed amount for one or two hubs; it writes nothing to the real score history.
- Q: Which scores are watched, and what threshold fires an alert? → A: Each hub's overall score and its five hazard scores; an alert fires when the absolute change is at least 2.0 points (configurable, one threshold for all).
- Q: How is triggering a check or the demo on the deployed service protected? → A: Both require an operator bearer token from configuration; with no token configured, both are disabled on the service. The command line needs no token. The alert list stays public.
- Q: Does the scheduled check's fresh data also become what chat and rankings use? → A: Yes. A check fetches data exactly like the refresh command (same location, atomic, a failed source keeps its old data), so alerts, rankings, and chat always describe the same data. The committed seed snapshot is never modified.

## User Scenarios & Testing *(mandatory)*

The users are the same as in feature 001. The **analyst** wants to know, without asking, when a hub's exposure picture changes. The **operator** (the developer or a reviewer) configures where alerts go, triggers checks on demand, and demonstrates the feature.

**Why scores can change at all.** Scores are computed only from data, so a score changes only when the data changes: a new FEMA National Risk Index release, revised weather history, or a change to the hub list or scoring configuration. The historical window is fixed, so on real data changes are rare. This feature therefore watches for change; it does not create change.

### User Story 1 - Get alerted when a hub's score changes (Priority: P1)

On a fixed schedule, the system fetches the latest public data, recomputes every hub's scores with the same deterministic engine as feature 001, and compares them with the last recorded scores. If a hub's score moved by at least the change threshold, the system records an alert and sends it to the configured destination. The alert names the hub, the score that changed, the old and new values, the size of the change, and the data sources and retrieval dates behind the new score.

**Why this priority**: this is the feature. Without detection and delivery, nothing else in this spec has value.

**Independent Test**: start from a recorded set of scores, change the data so one hub's score moves past the threshold, run one check, and verify that exactly one alert is recorded and delivered, with the right hub, old value, new value, and change.

**Acceptance Scenarios**:

1. **Given** recorded scores exist, **When** a check finds a hub's score moved by at least the threshold, **Then** one alert is recorded for that hub and score, with old value, new value, and change, all computed by code.
2. **Given** recorded scores exist, **When** a check finds no score moved by at least the threshold, **Then** no alert is recorded and the check itself is still recorded as having run.
3. **Given** no scores have ever been recorded, **When** the first check runs, **Then** it records the scores as the baseline and raises no alerts.
4. **Given** an alert destination is configured, **When** an alert is recorded, **Then** it is delivered to that destination; **Given** none is configured, **Then** the alert is still recorded and listed, and the check reports that delivery was skipped.

---

### User Story 2 - See recent alerts and checks (Priority: P1)

The analyst or operator opens a list of recent alerts, newest first, each showing the hub, the score that changed, old and new values, the change, when it was detected, whether delivery succeeded, and whether it came from a real check or a demonstration. The list is available without the language model.

**Why this priority**: delivery to an external destination can fail or be unconfigured; the recorded list is the reliable record and the main thing a reviewer will look at.

**Independent Test**: after recording alerts, request the list and verify order, fields, and the real/demo label.

**Acceptance Scenarios**:

1. **Given** alerts exist, **When** the list is requested, **Then** alerts are returned newest first with all fields above.
2. **Given** no alerts exist, **When** the list is requested, **Then** an empty list is returned along with when the last check ran and how many hubs it covered.
3. **Given** the service restarts, **When** the list is requested, **Then** previously recorded alerts and score history are still there.

---

### User Story 3 - Trigger a check on demand (Priority: P2)

The operator runs a check immediately, instead of waiting for the schedule, from the command line or through the deployed service, and sees a summary: hubs checked, alerts raised, and delivery outcome.

**Why this priority**: needed for demos and for verifying the deployment; the schedule alone makes the feature hard to show.

**Independent Test**: trigger a check and verify the summary matches what was recorded.

**Acceptance Scenarios**:

1. **Given** the operator presents the configured operator token (or uses the command line), **When** a check is triggered, **Then** it runs the same logic as the scheduled check and returns its summary.
2. **Given** a caller without the operator token, or a service with no token configured, **When** they try to trigger a check or a demonstration through the deployed service, **Then** the request is refused and nothing runs.
3. **Given** a check is already running, **When** another is triggered, **Then** the second does not run concurrently; the caller is told a check is in progress.

---

### User Story 4 - Demonstrate an alert (Priority: P2)

Because real data rarely changes, the operator can demonstrate the full path (detect, record, deliver, list) on demand. The demonstration produces a visible score change through the normal detection logic, and every alert it produces is clearly labeled as a demonstration, so it can never be mistaken for a real change.

**Why this priority**: a reviewer must be able to see the feature work during the interview.

**Independent Test**: run the demonstration and verify an alert labeled "demo" appears in the list and at the destination, and that real scores, rankings, and chat answers are unchanged afterwards.

**Acceptance Scenarios**:

1. **Given** the system is running, **When** the operator runs the demonstration, **Then** at least one alert labeled as a demonstration is recorded, delivered if a destination is configured, and listed.
2. **Given** a demonstration has run, **When** the analyst asks for rankings or chats, **Then** every score and answer is identical to before the demonstration.
3. **Given** a demonstration has run, **When** the next real check runs, **Then** it compares against real recorded scores only and raises no alert caused by the demonstration.

### Edge Cases

- **Data source down during a scheduled check**: the check uses the existing data for that source (as `refresh` does), records that the fetch failed, and still compares scores; a fetch failure alone never raises a score alert.
- **Destination down or slow**: delivery is attempted with a short time limit and a bounded number of attempts; the alert stays recorded with delivery marked failed; the check does not crash and the service keeps answering.
- **Destination returns an error status**: treated as a failed delivery, recorded, not retried forever.
- **Hub added or removed in the hub list**: a new hub gets a baseline and no alert; a removed hub produces no alert.
- **Change exactly equal to the threshold**: counts as a change (the rule is "at least the threshold").
- **Score changes slowly over many checks**: each check compares with the last recorded score, so a slow drift below the threshold per check is not alerted. This is a stated limit.
- **Service restarts mid-check**: history is never left half-written; the next check compares with the last complete recording.
- **Chat input mentions webhooks or alerts**: chat has no tool to read or change alert settings or trigger checks; alert configuration is unreachable from chat.

## Requirements *(mandatory)*

### Functional Requirements

**Detection**

- **FR-201**: The system MUST run a risk-change check on a fixed schedule while the service is running, with the interval set by configuration (default: once a day).
- **FR-202**: A check MUST fetch the latest public data the same way the refresh command does, into the same refreshed-data location, so the fetched data also becomes what rankings and chat use. It then recomputes scores with the unchanged feature-001 engine and records every hub's scores with the time and the data retrieval dates. A check MUST never modify the committed seed snapshot.
- **FR-203**: The scores watched MUST be each hub's overall score and each of its five hazard scores.
- **FR-204**: A change MUST be detected when the absolute difference between a watched score and that hub's last recorded value for the same score is at least the change threshold. The threshold MUST be set by configuration, in score points on the 0-100 scale (default: 2.0 points).
- **FR-205**: Change detection MUST be deterministic plain code: the same previous and current scores always give the same alerts. Old value, new value, and difference MUST be computed by code; no language model is involved anywhere in this feature.
- **FR-206**: The first check with no recorded history MUST record a baseline and raise no alerts. A hub with no previous record MUST get a baseline, not an alert.

**Recording**

- **FR-207**: Score history, checks, and alerts MUST persist across service restarts and redeploys, in storage on the persistent volume.
- **FR-208**: Each check MUST be recorded with start time, outcome, hubs checked, alerts raised, and any data-fetch failures.
- **FR-209**: Each alert MUST record: hub, score name, old value, new value, difference, detection time, whether it is real or a demonstration, the data retrieval dates behind the new value, and delivery status (delivered, failed with reason, or not configured).

**Delivery**

- **FR-210**: Alerts MUST be sent to a webhook destination taken only from configuration (environment). No API, chat message, or tool may set, read back, or change the destination. Constitution Principle VII.
- **FR-211**: Delivery MUST use a short time limit and a bounded number of attempts. A failed delivery MUST NOT stop the check or affect the rest of the service.
- **FR-212**: Every alert MUST also be written to the service log, whether or not a destination is configured.
- **FR-213**: The delivered message MUST be readable by a person in a common chat tool and also carry the structured alert fields for programs.

**Viewing and triggering**

- **FR-214**: The system MUST provide a list of recent alerts (newest first, bounded size) and the time and summary of the last check, without the language model, at `GET /api/alerts`.
- **FR-215**: The operator MUST be able to trigger a check on demand from the command line and from the deployed service. Triggering a check or a demonstration through the service MUST require an operator bearer token from configuration, compared in constant time; without a configured token, both MUST be refused on the service. The command line needs no token. The alert list (FR-214) is public.
- **FR-216**: Only one check MUST run at a time.

**Demonstration**

- **FR-217**: The system MUST provide a demonstration that drives at least one alert through the same detection, recording, delivery, and listing path. The demonstration compares today's real scores with a simulated previous set: a copy of them with a fixed, documented shift applied to one or two hubs' scores. The simulated set is never written to the real score history. Demonstration alerts MUST be labeled as such everywhere they appear, and a demonstration MUST NOT change real scores, real score history used for the next real check, rankings, or chat answers.

**Safety and scope**

- **FR-218**: Chat behavior, rankings, breakdowns, statistics, and the eval results of feature 001 MUST be unchanged on the same data. (A real check may bring newer data, exactly as the refresh command can; the scoring and answer logic do not change.) The agent gets no new tools in this feature.
- **FR-219**: Trigger and demonstration requests through the service MUST be rate-limited like chat, so a public URL cannot be used to hammer the public data providers.

### Key Entities

- **Score record**: one hub's watched scores (overall and five hazards) at one check, with the check it belongs to.
- **Check**: one run of the risk-change check: when, scheduled, manual, or demo, outcome, hubs checked, alerts raised, data-fetch failures, data retrieval dates.
- **Alert**: a detected change of one watched score for one hub: old value, new value, difference, detection time, real or demo, delivery status.
- **Alert destination**: a webhook address from configuration; never stored with alerts or exposed through any interface.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-201**: In tests, for every pair of previous and current scores, the alerts raised equal exactly the watched scores whose change is at least the threshold, with correct old value, new value, and difference (100% on the test set, including the boundary case).
- **SC-202**: A demonstration, run on the deployed service, produces a demo-labeled alert visible in the alert list within 1 minute of triggering, and at the configured destination when one is set.
- **SC-203**: After a restart or redeploy, 100% of previously recorded alerts and score history are still listed.
- **SC-204**: With the destination unreachable, a check still completes, records its alerts as failed deliveries, and chat keeps answering throughout.
- **SC-205**: After this feature ships, all feature-001 tests pass and the eval set still scores 20/20 on the default model.
- **SC-206**: No interface (chat, API, command line output, logs) reveals the configured destination address.

## Assumptions

- **One service instance.** The schedule runs inside the single service process; there is exactly one instance, so only one scheduler runs (Railway does not allow replicas with a volume anyway).
- **Missed runs are not caught up.** If the service is down at a scheduled time, that run is skipped; the next run compares with the last recorded scores, so a change is still caught, only later.
- **Threshold default 2.0 points** on the 0-100 scale: larger than rounding noise (scores are displayed to one decimal), small enough to catch a real data revision. A documented judgment call.
- **Daily default interval.** The underlying data changes at most a few times a year, so checking more often only adds load on free public data providers.
- **Webhook format.** A JSON POST with a human-readable `text` field (accepted by Slack-style incoming webhooks and generic catchers such as webhook.site) plus the structured alert fields.
- **History size.** Kept small and bounded (recent checks and alerts only); long-term retention is out of scope.
- **Out of scope:** alerts on forecasts or live weather events, per-user subscriptions, multiple destinations, email or SMS, alert acknowledgement, and alerts inside the chat page.
