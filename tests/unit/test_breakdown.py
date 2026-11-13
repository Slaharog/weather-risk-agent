import pytest

from weather_risk.scoring.engine import Engine, Hazard, UnknownHub


@pytest.fixture(scope="module")
def engine():
    return Engine.from_settings()


def test_breakdown_has_overall_score_and_rank(engine):
    b = engine.get_hub_breakdown("dallas")
    assert b.hub_id == "dallas"
    assert b.overall_score == pytest.approx(engine.scores["dallas"].score)
    expected_rank = next(r.rank for r in engine.rank_hubs("overall") if r.hub_id == "dallas")
    assert b.overall_rank == expected_rank
    assert b.hub_count == 16


def test_breakdown_has_every_hazard_with_rank_and_full_components(engine):
    b = engine.get_hub_breakdown("dallas")
    assert [h.hazard for h in b.hazards] == list(Hazard)
    for h in b.hazards:
        expected_rank = next(r.rank for r in engine.rank_hubs(h.hazard.value) if r.hub_id == "dallas")
        assert h.rank == expected_rank
        assert sum(c.contribution for c in h.components) == pytest.approx(h.score)
        for c in h.components:
            assert c.indicator and c.label and c.source
            assert c.raw_unit in {"events/yr", "days/yr"}
            assert 0 <= c.indicator_score <= 100


def test_unknown_hub_raises(engine):
    with pytest.raises(UnknownHub):
        engine.get_hub_breakdown("boston")
