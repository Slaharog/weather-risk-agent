import pytest
from pydantic import ValidationError

from weather_risk.agent.schemas import (
    AgentAnswer,
    CompareArgs,
    RankArgs,
    StatArgs,
    openai_strict_schema,
)


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_agent_answer_schema_is_strict_compatible():
    schema = openai_strict_schema(AgentAnswer)
    for node in _walk(schema):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])


def test_agent_answer_enums_and_nullable_question():
    props = openai_strict_schema(AgentAnswer)["properties"]
    assert props["answer_type"]["enum"] == ["answer", "clarification", "refusal"]
    question_types = {t.get("type") for t in props["clarifying_question"]["anyOf"]}
    assert question_types == {"string", "null"}
    schema = openai_strict_schema(AgentAnswer)
    levels = next(n["enum"] for n in _walk(schema) if "enum" in n and "high" in n["enum"])
    assert levels == ["low", "medium", "high"]


def test_agent_answer_has_no_numeric_fields():
    """The LLM's output carries no numbers of its own: numbers come from tools (Principle I)."""
    for node in _walk(openai_strict_schema(AgentAnswer)):
        assert node.get("type") not in {"number", "integer"}


def test_rank_limit_bounds():
    assert RankArgs(hazard="winter", region=None, limit=None).limit is None
    RankArgs(hazard="winter", region="Midwest", limit=16)
    for bad in (0, 17):
        with pytest.raises(ValidationError):
            RankArgs(hazard="winter", region=None, limit=bad)


@pytest.mark.parametrize("hub_ids, hazards", [
    (["miami"], ["flood"]),
    (["miami", "miami"], ["flood"]),
    (["miami", "houston", "dallas", "denver", "phoenix", "chicago", "detroit"], ["flood"]),
    (["miami", "houston"], []),
    (["miami", "houston"], ["flood", "flood"]),
    (["miami", "boston"], ["flood"]),
])
def test_compare_argument_limits(hub_ids, hazards):
    with pytest.raises(ValidationError):
        CompareArgs(hub_ids=hub_ids, hazards=hazards)


@pytest.mark.parametrize("year", [2015, 2026])
def test_stat_year_bounds(year):
    with pytest.raises(ValidationError):
        StatArgs(hub_id="denver", stat="snowfall_days_pct", year=year)


def test_unknown_values_are_rejected_by_enums():
    with pytest.raises(ValidationError):
        RankArgs(hazard="earthquake", region=None, limit=None)
    with pytest.raises(ValidationError):
        StatArgs(hub_id="boston", stat="snowfall_days_pct", year=2025)
