"""Risk-change detection: pure functions, no I/O, no LLM (spec 002 FR-203..FR-206, FR-217).

Scores are compared exactly as they are displayed (one decimal), so an alert's old value,
new value and change always match what rankings and chat show (research.md §3).
"""

import copy

from pydantic import BaseModel

from weather_risk.scoring.engine import METRICS, Engine

Scores = dict[str, dict[str, float]]  # hub_id -> metric -> score (one decimal)

# The demo's simulated previous scores (research.md §5): today's scores with these shifts.
# Dallas heat 7.5 lower -> the demo shows it rising 7.5; Houston hurricane 5.0 higher -> falling 5.0.
# If a shift would leave the 0-100 scale, it is applied in the other direction instead, so the
# demo always shows the full move (code review: clamping could hide it, e.g. Dallas heat in winter).
DEMO_SHIFTS: dict[tuple[str, str], float] = {("dallas", "heat"): -7.5, ("houston", "hurricane"): +5.0}


class Change(BaseModel):
    hub_id: str
    metric: str
    old: float
    new: float
    change: float  # new - old, rounded to one decimal; negative = the score fell


def watched_scores(engine: Engine) -> Scores:
    """Every hub's overall score and five hazard scores, rounded as displayed."""
    return {hub_id: {m: round(engine.metric_score(hub_id, m), 1) for m in METRICS}
            for hub_id in engine.scores}


def detect_changes(previous: Scores, current: Scores, threshold: float) -> list[Change]:
    """Scores that moved by at least `threshold` points. Hubs or metrics missing on either side
    are skipped: a new hub becomes part of the baseline, a removed hub is ignored."""
    if threshold <= 0:
        raise ValueError("threshold must be greater than 0")
    changes = []
    for hub_id in sorted(previous.keys() & current.keys()):
        for metric in sorted(previous[hub_id].keys() & current[hub_id].keys()):
            old, new = previous[hub_id][metric], current[hub_id][metric]
            change = round(new - old, 1)
            if abs(change) >= threshold:
                changes.append(Change(hub_id=hub_id, metric=metric, old=old, new=new, change=change))
    return changes


def simulate_previous(current: Scores) -> Scores:
    """A copy of `current` with DEMO_SHIFTS applied, kept on the 0-100 scale. Never stored."""
    previous = copy.deepcopy(current)
    for (hub_id, metric), shift in DEMO_SHIFTS.items():
        if metric in previous.get(hub_id, {}):
            value = previous[hub_id][metric]
            if not 0.0 <= value + shift <= 100.0:
                shift = -shift
            previous[hub_id][metric] = round(value + shift, 1)
    return previous
