import json

from weather_risk.agent.conversations import ConversationStore, trim
from weather_risk.agent.llm import FunctionCall, LlmTurn
from weather_risk.agent.loop import run_turn
from weather_risk.agent.tools import ToolRegistry
from weather_risk.scoring.engine import Engine

ANSWER = json.dumps({"answer_type": "answer", "narrative": "ok", "assumptions": [],
                     "limitations": [], "confidence": {"level": "high", "reason": "r"},
                     "clarifying_question": None})


class RecordingLlm:
    """First turn of each user message calls rank_hubs; then answers. Records what it was sent."""

    def __init__(self):
        self.sent = []

    def respond(self, instructions, input_items, tools, answer_schema):
        self.sent.append(list(input_items))
        if input_items[-1].get("role") == "user":
            args = json.dumps({"hazard": "winter", "region": "Midwest", "limit": None})
            return LlmTurn(items=[{"type": "function_call", "name": "rank_hubs",
                                   "arguments": args, "call_id": f"c{len(self.sent)}"}],
                           function_calls=[FunctionCall("rank_hubs", args, f"c{len(self.sent)}")])
        return LlmTurn(items=[{"type": "message", "content": ANSWER}], text=ANSWER)


def test_follow_up_sees_earlier_turns_including_tool_results():
    store, llm = ConversationStore(), RecordingLlm()
    tools = ToolRegistry(Engine.from_settings())
    convo = store.get_or_create(None)
    run_turn(convo, "Midwest winter ranking?", llm, tools)
    store.save(convo)
    run_turn(store.get_or_create(convo.id), "Why is the first one so high?", llm, tools)

    second_question_input = llm.sent[2]
    assert second_question_input[0] == {"role": "user", "content": "Midwest winter ranking?"}
    outputs = [i for i in second_question_input if i.get("type") == "function_call_output"]
    assert "Minneapolis" in outputs[0]["output"]  # earlier tool result is in context
    assert second_question_input[-1] == {"role": "user", "content": "Why is the first one so high?"}


def test_new_conversation_sends_no_earlier_context():
    store, llm = ConversationStore(), RecordingLlm()
    tools = ToolRegistry(Engine.from_settings())
    first = store.get_or_create(None)
    run_turn(first, "Midwest winter ranking?", llm, tools)
    store.save(first)
    run_turn(store.get_or_create(None), "What about Chicago?", llm, tools)
    assert llm.sent[2] == [{"role": "user", "content": "What about Chicago?"}]


def test_trim_keeps_the_last_20_user_turns_and_cuts_only_at_user_messages():
    items = []
    for i in range(25):
        items += [{"role": "user", "content": f"q{i}"},
                  {"type": "function_call", "call_id": f"c{i}"},
                  {"type": "function_call_output", "call_id": f"c{i}"}]
    kept = trim(items)
    users = [i["content"] for i in kept if i.get("role") == "user"]
    assert users == [f"q{i}" for i in range(5, 25)]
    assert kept[0] == {"role": "user", "content": "q5"}


def test_store_keeps_at_most_200_conversations_dropping_the_oldest():
    store = ConversationStore()
    first = store.get_or_create(None)
    for _ in range(200):
        store.get_or_create(None)
    assert len(store) == 200
    assert store.get_or_create(first.id).id != first.id  # oldest was dropped
