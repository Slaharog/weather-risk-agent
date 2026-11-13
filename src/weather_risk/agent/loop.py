"""The agent loop: a plain tool-calling loop, no framework (constitution Principle V).

One user message:
1. Send the conversation, the tool list, and the answer schema to the model.
2. If the model asks for tools, run them (allow-list, validated arguments) and send results back.
3. When the model answers, validate the answer against the schema; retry once if invalid.
4. Build the response: the model's narrative + tables and sources built by code from tool results.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from pydantic import ValidationError

from weather_risk.agent.llm import LlmClient, LlmUnavailable, tool_result_item
from weather_risk.agent.prompts import SYSTEM_PROMPT
from weather_risk.agent.schemas import (
    AgentAnswer,
    ChatResponse,
    ToolCallInfo,
    openai_strict_schema,
)
from weather_risk.agent.tools import ToolOutcome

MAX_MODEL_CALLS = 6
ANSWER_SCHEMA = openai_strict_schema(AgentAnswer)

INVALID_ANSWER_ERROR = "Sorry, I could not produce a valid answer. Please rephrase the question."
TOO_MANY_STEPS_ERROR = "Sorry, that question needed too many steps. Please ask something narrower."
LLM_DOWN_ERROR = "The language model is unavailable right now. Scores are still available at /api/rankings."


class Tools(Protocol):
    def specs(self) -> list[dict]: ...
    def execute(self, name: str, arguments: str) -> ToolOutcome: ...


@dataclass
class Conversation:
    id: str
    items: list[dict] = field(default_factory=list)  # user messages, model items, tool results
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Serializes turns on one conversation, so two concurrent requests cannot lose a turn.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def new(cls) -> "Conversation":
        return cls(id=str(uuid.uuid4()))


def _dedupe(sources: list[dict]) -> list[dict]:
    seen, out = set(), []
    for s in sources:
        key = (s["name"], s["period"])
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def run_turn(conversation: Conversation, message: str, llm: LlmClient, tools: Tools) -> ChatResponse:
    items = [*conversation.items, {"role": "user", "content": message}]
    outcomes: list[ToolOutcome] = []
    retried = False
    discarded: list[dict] = []  # invalid answer + retry prompt: sent once, never saved

    def fail(error: str) -> ChatResponse:
        # The failed turn is not saved, so the conversation history stays clean.
        return ChatResponse(conversation_id=conversation.id, answer=None, error=error)

    for _ in range(MAX_MODEL_CALLS):
        try:
            turn = llm.respond(SYSTEM_PROMPT, items, tools.specs(), ANSWER_SCHEMA)
        except LlmUnavailable:
            return fail(LLM_DOWN_ERROR)
        items += turn.items

        if turn.function_calls:
            for call in turn.function_calls:
                outcome = tools.execute(call.name, call.arguments)
                outcomes.append(outcome)
                items.append(tool_result_item(call.call_id, outcome.result))
            continue

        try:
            answer = AgentAnswer.model_validate_json(turn.text or "")
        except ValidationError as exc:
            if retried:
                return fail(INVALID_ANSWER_ERROR)
            retried = True
            retry_prompt = {"role": "user", "content":
                            "Your last answer did not match the required JSON schema: "
                            f"{exc.errors(include_url=False)}. Reply again with a valid answer."}
            items.append(retry_prompt)
            discarded += [*turn.items, retry_prompt]
            continue

        # Missing data is reported by code, not left to the model (data-model.md section 5).
        ok = [o for o in outcomes if o.ok]
        missing = sorted({m for o in ok for m in o.missing})
        if missing:
            answer.limitations.append(
                "Some data was unavailable; affected scores use the remaining indicators "
                f"with re-normalized weights: {', '.join(missing)}.")
            if answer.confidence.level == "high":
                answer.confidence.level = "medium"
                answer.confidence.reason += " (lowered: some data was missing)"

        conversation.items = [i for i in items if not any(i is d for d in discarded)]
        conversation.updated_at = datetime.now(UTC)
        return ChatResponse(
            conversation_id=conversation.id,
            answer=answer,
            tables=[o.table for o in ok if o.table is not None],
            data_sources=_dedupe([s for o in ok for s in o.sources]),
            tool_calls=[ToolCallInfo(tool=o.tool, arguments=o.arguments) for o in outcomes],
        )

    return fail(TOO_MANY_STEPS_ERROR)
