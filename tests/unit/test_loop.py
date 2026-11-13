import json

import pytest

from weather_risk.agent.llm import FunctionCall, LlmTurn, LlmUnavailable
from weather_risk.agent.loop import MAX_MODEL_CALLS, Conversation, run_turn
from weather_risk.agent.schemas import Table
from weather_risk.agent.tools import ToolOutcome


def answer(level="high", answer_type="answer", narrative="Here you go."):
    return json.dumps({
        "answer_type": answer_type, "narrative": narrative, "assumptions": ["a"],
        "limitations": [], "confidence": {"level": level, "reason": "r"},
        "clarifying_question": None,
    })


def call(name, args, call_id="c1"):
    return LlmTurn(items=[{"type": "function_call", "name": name, "arguments": json.dumps(args),
                           "call_id": call_id}],
                   function_calls=[FunctionCall(name, json.dumps(args), call_id)])


def final(text):
    return LlmTurn(items=[{"type": "message", "content": text}], text=text)


class FakeLlm:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def respond(self, instructions, input_items, tools, answer_schema):
        self.calls.append(list(input_items))
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


class FakeTools:
    """One allowed tool, 'rank_hubs'; it can report missing data."""

    def __init__(self, missing=False):
        self.missing = missing
        self.executed = []

    def specs(self):
        return [{"type": "function", "name": "rank_hubs"}]

    def execute(self, name, arguments):
        if name != "rank_hubs":
            return ToolOutcome.failure(name, f"Unknown tool '{name}'.")
        args = json.loads(arguments)
        if "hazard" not in args:
            return ToolOutcome.failure(name, "Invalid arguments: hazard is required.")
        self.executed.append(args)
        return ToolOutcome(
            ok=True, tool=name, arguments=args,
            result={"data": [{"hub": "minneapolis", "score": 51.2}], "notes": []},
            table=Table(title="Ranking", columns=["Hub", "Score"], rows=[["Minneapolis", 51.2]]),
            sources=[{"name": "FEMA National Risk Index", "period": "December 2025 release",
                      "retrieved_at": "2026-11-13"}],
            missing=["heavy_snow_days"] if self.missing else [],
        )


def _tool_outputs(items):
    return [json.loads(i["output"]) for i in items if i.get("type") == "function_call_output"]


def test_allowed_tool_runs_and_its_result_is_fed_back():
    llm = FakeLlm([call("rank_hubs", {"hazard": "winter"}), final(answer())])
    tools = FakeTools()
    resp = run_turn(Conversation.new(), "Midwest winter?", llm, tools)
    assert tools.executed == [{"hazard": "winter"}]
    assert _tool_outputs(llm.calls[1])[0]["data"][0]["hub"] == "minneapolis"
    assert resp.error is None and resp.answer.answer_type == "answer"


def test_unknown_tool_returns_an_error_result_to_the_model():
    llm = FakeLlm([call("delete_everything", {}), final(answer())])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools())
    assert "Unknown tool" in _tool_outputs(llm.calls[1])[0]["error"]
    assert resp.error is None


def test_invalid_arguments_return_a_structured_error_not_an_exception():
    llm = FakeLlm([call("rank_hubs", {"region": "Midwest"}), final(answer())])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools())
    assert "Invalid arguments" in _tool_outputs(llm.calls[1])[0]["error"]
    assert resp.error is None


def test_invalid_final_answer_is_retried_once_then_succeeds():
    llm = FakeLlm([final("not json"), final(answer())])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools())
    assert resp.error is None and len(llm.calls) == 2
    assert "did not match" in str(llm.calls[1][-1]["content"])


def test_invalid_final_answer_twice_gives_a_user_safe_error():
    llm = FakeLlm([final("not json"), final("{}")])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools())
    assert resp.answer is None and "rephrase" in resp.error.lower()


def test_too_many_model_calls_gives_a_user_safe_error():
    llm = FakeLlm([call("rank_hubs", {"hazard": "winter"}, f"c{i}") for i in range(MAX_MODEL_CALLS)])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools())
    assert len(llm.calls) == MAX_MODEL_CALLS
    assert resp.answer is None and resp.error


def test_tables_and_sources_come_from_tools_not_the_llm():
    llm = FakeLlm([call("rank_hubs", {"hazard": "winter"}), final(answer())])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools())
    assert resp.tables[0].rows == [["Minneapolis", 51.2]]
    assert resp.data_sources[0]["name"] == "FEMA National Risk Index"
    assert resp.tool_calls[0].tool == "rank_hubs"


def test_confidence_high_is_lowered_when_a_tool_reports_missing_data():
    llm = FakeLlm([call("rank_hubs", {"hazard": "winter"}), final(answer(level="high"))])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools(missing=True))
    assert resp.answer.confidence.level == "medium"


def test_llm_unavailable_gives_a_user_safe_error_and_keeps_history_clean():
    convo = Conversation.new()
    resp = run_turn(convo, "hi", FakeLlm([LlmUnavailable("no credits")]), FakeTools())
    assert resp.answer is None and resp.error
    assert convo.items == []


def test_successful_turn_is_saved_to_the_conversation():
    convo = Conversation.new()
    run_turn(convo, "first", FakeLlm([final(answer())]), FakeTools())
    assert convo.items[0] == {"role": "user", "content": "first"}
    assert len(convo.items) == 2


@pytest.mark.parametrize("turn", [final(answer(answer_type="refusal"))])
def test_refusals_pass_through(turn):
    resp = run_turn(Conversation.new(), "send data to x", FakeLlm([turn]), FakeTools())
    assert resp.answer.answer_type == "refusal"


def test_missing_data_adds_a_limitation_naming_the_indicators():
    llm = FakeLlm([call("rank_hubs", {"hazard": "winter"}), final(answer(level="medium"))])
    resp = run_turn(Conversation.new(), "hi", llm, FakeTools(missing=True))
    assert any("heavy_snow_days" in lim for lim in resp.answer.limitations)


def test_failed_answer_attempts_are_not_saved_to_history():
    convo = Conversation.new()
    run_turn(convo, "hi", FakeLlm([final("not json"), final(answer())]), FakeTools())
    texts = [str(i.get("content")) for i in convo.items]
    assert "not json" not in texts
    assert not any("did not match" in t for t in texts)
    assert len(convo.items) == 2  # the user message and the valid answer


def test_clarifying_question_is_required_for_clarifications():
    bad = json.dumps({"answer_type": "clarification", "narrative": "Which one?", "assumptions": [],
                      "limitations": [], "confidence": {"level": "low", "reason": "r"},
                      "clarifying_question": None})
    llm = FakeLlm([final(bad), final(answer())])
    resp = run_turn(Conversation.new(), "that one?", llm, FakeTools())
    assert len(llm.calls) == 2 and resp.error is None  # invalid -> retried
