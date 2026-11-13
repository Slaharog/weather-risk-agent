"""The only module that talks to an LLM provider (constitution Principle II).

Swapping providers means writing another class with the same `respond` method.
The loop depends on the `LlmClient` protocol, so tests use a fake instead of the network.
"""

import json
import ssl
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from weather_risk.settings import get_settings


class LlmUnavailable(Exception):
    """The provider could not be reached or refused the request (key, credits, outage)."""


@dataclass
class FunctionCall:
    name: str
    arguments: str  # raw JSON text from the model; validated by our code before use
    call_id: str


@dataclass
class LlmTurn:
    items: list[dict]  # the model's output items, to append to the conversation as-is
    function_calls: list[FunctionCall] = field(default_factory=list)
    text: str | None = None  # final answer text (JSON) when there are no function calls
    input_tokens: int = 0
    output_tokens: int = 0


class LlmClient(Protocol):
    def respond(self, instructions: str, input_items: list[dict], tools: list[dict],
                answer_schema: dict) -> LlmTurn: ...


def tool_result_item(call_id: str, result: dict) -> dict:
    return {"type": "function_call_output", "call_id": call_id, "output": json.dumps(result)}


class OpenAILlm:
    """OpenAI Responses API with strict function tools and a strict final-answer schema."""

    def __init__(self) -> None:
        from openai import OpenAI

        s = get_settings()
        if not s.openai_api_key:
            raise LlmUnavailable("OPENAI_API_KEY is not set")
        self.model = s.openai_model
        self.effort = s.openai_reasoning_effort
        # OS certificate store, so TLS works behind proxies/antivirus that re-sign certificates.
        self.client = OpenAI(api_key=s.openai_api_key, timeout=60, max_retries=2,
                             http_client=httpx.Client(verify=ssl.create_default_context()))

    def respond(self, instructions: str, input_items: list[dict], tools: list[dict],
                answer_schema: dict) -> LlmTurn:
        import openai

        try:
            r = self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=input_items,
                tools=tools,
                text={"format": {"type": "json_schema", "name": "agent_answer",
                                 "strict": True, "schema": answer_schema}},
                reasoning={"effort": self.effort},
                store=False,  # we keep the conversation ourselves (provider stays swappable)
                include=["reasoning.encrypted_content"],  # lets reasoning items be sent back
            )
        except openai.OpenAIError as exc:
            raise LlmUnavailable(f"{type(exc).__name__}: {str(exc)[:200]}") from exc

        return self._turn(r)

    def complete_json(self, instructions: str, text: str, name: str, schema: dict) -> dict:
        """One-shot strict-JSON completion with no tools (used by the optional eval judge)."""
        import openai

        try:
            r = self.client.responses.create(
                model=self.model, instructions=instructions, input=text, store=False,
                text={"format": {"type": "json_schema", "name": name, "strict": True,
                                 "schema": schema}},
                reasoning={"effort": self.effort})
        except openai.OpenAIError as exc:
            raise LlmUnavailable(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
        return json.loads(r.output_text)

    @staticmethod
    def _turn(r) -> LlmTurn:
        calls = [FunctionCall(o.name, o.arguments, o.call_id)
                 for o in r.output if o.type == "function_call"]
        return LlmTurn(
            items=[o.model_dump(exclude_none=True) for o in r.output],
            function_calls=calls,
            text=None if calls else r.output_text,
            input_tokens=r.usage.input_tokens if r.usage else 0,
            output_tokens=r.usage.output_tokens if r.usage else 0,
        )
