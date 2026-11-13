"""Plausibility tests: do the scores on the REAL seed data agree with well-known US climate?

Written before looking at any real score (data-model.md section 5). If one fails, look for a
bug or a data problem first. A weight or cap may change only with a dated entry in
docs/decisions.md explaining why, never just to make this test pass.
"""

import pytest

from weather_risk.scoring.engine import Engine, Hazard

pytestmark = pytest.mark.plausibility


@pytest.fixture(scope="module")
def ranked():
    engine = Engine.from_settings()

    def order(hazard: Hazard) -> list[str]:
        return sorted(engine.scores, key=lambda h: -engine.scores[h].hazards[hazard].score)

    return engine, order


def test_miami_and_houston_are_top_two_for_hurricane(ranked):
    _, order = ranked
    assert set(order(Hazard.HURRICANE)[:2]) == {"miami", "houston"}


def test_phoenix_and_dallas_are_top_two_for_heat(ranked):
    _, order = ranked
    assert set(order(Hazard.HEAT)[:2]) == {"phoenix", "dallas"}


def test_minneapolis_is_top_three_for_winter(ranked):
    _, order = ranked
    assert "minneapolis" in order(Hazard.WINTER)[:3]


def test_los_angeles_is_bottom_three_for_winter(ranked):
    _, order = ranked
    assert "los-angeles" in order(Hazard.WINTER)[-3:]


def test_denver_hurricane_score_is_zero(ranked):
    engine, _ = ranked
    assert engine.scores["denver"].hazards[Hazard.HURRICANE].score == 0
