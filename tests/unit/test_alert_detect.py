"""Change detection (spec 002 FR-203..FR-206, FR-217; data-model.md §1-2). Written test-first."""

import pytest

from weather_risk.alerts.detect import (
    DEMO_SHIFTS,
    Change,
    detect_changes,
    simulate_previous,
    watched_scores,
)
from weather_risk.scoring.engine import METRICS, Engine


@pytest.fixture
def seed_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))  # empty live dir: the committed seed is used
    return Engine.from_settings()


def test_watched_scores_are_every_hub_and_metric_rounded_as_displayed(seed_engine):
    scores = watched_scores(seed_engine)
    assert len(scores) == 16
    assert all(set(m) == set(METRICS) for m in scores.values())
    assert scores["dallas"]["heat"] == round(seed_engine.metric_score("dallas", "heat"), 1)


def test_change_of_exactly_the_threshold_alerts_and_just_below_does_not():
    previous = {"a": {"overall": 30.0, "heat": 30.0}}
    current = {"a": {"overall": 32.0, "heat": 31.9}}
    assert detect_changes(previous, current, 2.0) == [
        Change(hub_id="a", metric="overall", old=30.0, new=32.0, change=2.0)]


def test_decreases_alert_with_a_negative_change():
    changes = detect_changes({"a": {"flood": 50.0}}, {"a": {"flood": 44.7}}, 2.0)
    assert changes == [Change(hub_id="a", metric="flood", old=50.0, new=44.7, change=-5.3)]


def test_change_is_rounded_to_one_decimal():
    # 0.1 + 2.2 is 2.3000000000000003 in floating point; the stored change must be 2.3 exactly.
    [c] = detect_changes({"a": {"heat": 0.1}}, {"a": {"heat": 2.4}}, 2.0)
    assert c.change == 2.3


def test_first_check_has_no_previous_scores_and_raises_nothing():
    assert detect_changes({}, {"a": {"overall": 10.0}}, 2.0) == []


def test_new_and_removed_hubs_raise_nothing():
    previous = {"old": {"overall": 10.0}, "kept": {"overall": 10.0}}
    current = {"new": {"overall": 90.0}, "kept": {"overall": 10.0}}
    assert detect_changes(previous, current, 2.0) == []


def test_output_is_sorted_by_hub_then_metric():
    previous = {"b": {"heat": 0.0, "flood": 0.0}, "a": {"winter": 0.0}}
    current = {"b": {"heat": 9.0, "flood": 9.0}, "a": {"winter": 9.0}}
    keys = [(c.hub_id, c.metric) for c in detect_changes(previous, current, 2.0)]
    assert keys == [("a", "winter"), ("b", "flood"), ("b", "heat")]


@pytest.mark.parametrize("threshold", [0, -1])
def test_threshold_must_be_positive(threshold):
    with pytest.raises(ValueError):
        detect_changes({}, {}, threshold)


def test_demo_shifts_dallas_heat_down_and_houston_hurricane_up():
    assert DEMO_SHIFTS == {("dallas", "heat"): -7.5, ("houston", "hurricane"): +5.0}
    current = {"dallas": {"heat": 84.1, "overall": 46.0}, "houston": {"hurricane": 60.1}}
    previous = simulate_previous(current)
    assert previous == {"dallas": {"heat": 76.6, "overall": 46.0}, "houston": {"hurricane": 65.1}}
    assert current["dallas"]["heat"] == 84.1  # input not mutated


def test_demo_skips_a_missing_hub():
    assert simulate_previous({"miami": {"heat": 50.0}}) == {"miami": {"heat": 50.0}}


def test_demo_on_real_scores_gives_exactly_two_alerts(seed_engine):
    current = watched_scores(seed_engine)
    changes = detect_changes(simulate_previous(current), current, 2.0)
    assert [(c.hub_id, c.metric, c.change) for c in changes] == [
        ("dallas", "heat", 7.5), ("houston", "hurricane", -5.0)]


def test_blank_alert_secrets_mean_not_configured():
    from weather_risk.settings import Settings

    s = Settings(alert_webhook_url="  ", alert_admin_token="")
    assert s.alert_webhook_url is None and s.alert_admin_token is None


def test_demo_shift_flips_direction_instead_of_clamping():
    # In winter Dallas heat may be near 0: subtracting 7.5 would clamp and lose the alert.
    previous = simulate_previous({"dallas": {"heat": 1.0}, "houston": {"hurricane": 98.0}})
    assert previous == {"dallas": {"heat": 8.5}, "houston": {"hurricane": 93.0}}
    changes = detect_changes(previous, {"dallas": {"heat": 1.0}, "houston": {"hurricane": 98.0}}, 2.0)
    assert [abs(c.change) for c in changes] == [7.5, 5.0]
