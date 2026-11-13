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
    from weather_risk.api.limits import RateLimiter

    monkeypatch.setattr(app_module, "get_llm", lambda: EchoLlm())
    monkeypatch.setattr(app_module, "limiter", RateLimiter(per_minute=1000, per_day=1000))


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


def test_oversized_body_is_rejected_before_parsing(fake_llm):
    r = client.post("/api/chat", content=b'{"message": "' + b"x" * 20_000 + b'"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_rate_limit_returns_429(fake_llm, monkeypatch):
    from weather_risk.api.limits import RateLimiter

    monkeypatch.setattr(app_module, "limiter", RateLimiter(per_minute=1, per_day=100))
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 429


def test_trusted_ip_header_gives_each_client_its_own_limit(fake_llm, monkeypatch):
    """Behind Railway's proxy every request comes from the proxy; X-Real-IP names the client."""
    from weather_risk.api.limits import RateLimiter

    monkeypatch.setattr(app_module, "limiter", RateLimiter(per_minute=1, per_day=100))
    monkeypatch.setattr(app_module, "TRUSTED_IP_HEADER", "X-Real-IP")
    a = client.post("/api/chat", json={"message": "hi"}, headers={"X-Real-IP": "203.0.113.1"})
    b = client.post("/api/chat", json={"message": "hi"}, headers={"X-Real-IP": "203.0.113.2"})
    again = client.post("/api/chat", json={"message": "hi"}, headers={"X-Real-IP": "203.0.113.1"})
    assert (a.status_code, b.status_code, again.status_code) == (200, 200, 429)


def test_ip_header_is_ignored_unless_configured(fake_llm, monkeypatch):
    """Without a trusted proxy, a client could set X-Real-IP itself to dodge the limit."""
    from weather_risk.api.limits import RateLimiter

    monkeypatch.setattr(app_module, "limiter", RateLimiter(per_minute=1, per_day=100))
    monkeypatch.setattr(app_module, "TRUSTED_IP_HEADER", None)
    a = client.post("/api/chat", json={"message": "hi"}, headers={"X-Real-IP": "203.0.113.1"})
    b = client.post("/api/chat", json={"message": "hi"}, headers={"X-Real-IP": "203.0.113.2"})
    assert (a.status_code, b.status_code) == (200, 429)


def test_chat_page_has_voice_input_with_fallback_and_no_auto_send():
    """Spec 003: mic control, announced status, unsupported note, privacy hint, no auto-send."""
    page = client.get("/").text
    assert 'id="mic"' in page and 'aria-pressed="false"' in page
    assert 'id="voice-status"' in page and 'role="status"' in page
    assert "Voice input isn't supported in this browser" in page
    assert "Voice uses your browser's speech service" in page
    voice_code = page[page.index("function initVoice("):page.index("// end initVoice")]
    for forbidden in ("requestSubmit", ".submit(", "ask("):
        assert forbidden not in voice_code  # voice fills the box; only Send sends
