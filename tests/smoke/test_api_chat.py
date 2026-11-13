import json

import pytest
from fastapi.testclient import TestClient

from weather_risk.agent.llm import LlmTurn, LlmUnavailable
from weather_risk.api import app as app_module

client = TestClient(app_module.app)

ANSWER = json.dumps({"answer_type": "answer", "narrative": "Fine.", "assumptions": [],
                     "limitations": [], "confidence": {"level": "high", "reason": "r"},
                     "clarifying_question": None})


class EchoLlm:
    def respond(self, instructions, input_items, tools, answer_schema):
        return LlmTurn(items=[{"type": "message", "content": ANSWER}], text=ANSWER)


@pytest.fixture
def fake_llm(monkeypatch):
    monkeypatch.setattr(app_module, "get_llm", lambda: EchoLlm())


def test_index_serves_the_chat_page():
    r = client.get("/")
    assert r.status_code == 200 and "Hub Weather Risk" in r.text


@pytest.mark.parametrize("message", ["", "   ", "x" * 1001])
def test_message_length_is_validated(fake_llm, message):
    assert client.post("/api/chat", json={"message": message}).status_code == 422


def test_missing_key_gives_503(monkeypatch):
    def no_key():
        raise LlmUnavailable("OPENAI_API_KEY is not set")

    monkeypatch.setattr(app_module, "get_llm", no_key)
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 503


def test_unknown_conversation_id_starts_a_new_conversation(fake_llm):
    r = client.post("/api/chat", json={"conversation_id": "not-a-real-id", "message": "hi"})
    body = r.json()
    assert r.status_code == 200
    assert body["conversation_id"] != "not-a-real-id"
    assert body["answer"]["narrative"] == "Fine."


def test_same_conversation_id_is_kept(fake_llm):
    first = client.post("/api/chat", json={"message": "hi"}).json()
    second = client.post("/api/chat", json={"conversation_id": first["conversation_id"],
                                            "message": "again"}).json()
    assert second["conversation_id"] == first["conversation_id"]
