"""The contracts between the LLM and our code (contracts/agent-tools.md, data-model.md section 7).

Two layers of enforcement:
1. OpenAI strict mode: the model can only produce JSON matching these schemas.
2. Pydantic validation in our code: limits strict mode cannot express (ranges, uniqueness)
   are checked again before any tool runs or any answer is shown.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from weather_risk.hubs import Region, load_hubs
from weather_risk.scoring.stats import FIRST_YEAR, LAST_YEAR, STATS

# Built from config/hubs.toml, so the model can only name hubs that exist.
HubId = StrEnum("HubId", {h.id.upper().replace("-", "_"): h.id for h in load_hubs()})
StatName = StrEnum("StatName", {name.upper(): name for name in STATS})
HazardOrOverall = Literal["overall", "winter", "heat", "flood", "hurricane", "severe_storms"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- tool arguments ----------

class CoverageArgs(_Strict):
    pass


class RankArgs(_Strict):
    hazard: HazardOrOverall = Field(description="'overall' or one hazard.")
    region: Region | None = Field(description="US Census region, or null for all hubs.")
    limit: int | None = Field(ge=1, le=16, description="Max rows (1-16), or null for all.")


class BreakdownArgs(_Strict):
    hub_id: HubId


def _unique(values: list) -> list:
    if len(set(values)) != len(values):
        raise ValueError("values must be unique")
    return values


class CompareArgs(_Strict):
    hub_ids: list[HubId] = Field(min_length=2, max_length=6, description="2-6 different hubs.")
    hazards: list[HazardOrOverall] = Field(min_length=1, max_length=6,
                                           description="1-6 different hazards or 'overall'.")

    _check_hubs = field_validator("hub_ids")(_unique)
    _check_hazards = field_validator("hazards")(_unique)


class StatArgs(_Strict):
    hub_id: HubId
    stat: StatName
    year: int = Field(ge=FIRST_YEAR, le=LAST_YEAR,
                      description=f"Calendar year {FIRST_YEAR}-{LAST_YEAR}; 'last year' = {LAST_YEAR}.")


# ---------- the final answer the LLM must return ----------

class Confidence(_Strict):
    level: Literal["low", "medium", "high"]
    reason: str = Field(description="One line: why this confidence level.")


class AgentAnswer(_Strict):
    """No numeric fields on purpose: numbers shown to the user come from tools (Principle I)."""

    answer_type: Literal["answer", "clarification", "refusal"]
    narrative: str = Field(description="Explanation in words. Only use numbers that appear in "
                                       "tool results; tables with the numbers are shown separately.")
    assumptions: list[str]
    limitations: list[str]
    confidence: Confidence
    clarifying_question: str | None = Field(description="Only when answer_type is 'clarification'.")

    @model_validator(mode="after")
    def _question_matches_type(self) -> "AgentAnswer":
        if self.answer_type == "clarification" and not (self.clarifying_question or "").strip():
            raise ValueError("answer_type 'clarification' requires a clarifying_question")
        if self.answer_type != "clarification":
            self.clarifying_question = None  # ignore a stray question on other answer types
        return self


# ---------- what the API returns (built by code, not by the LLM) ----------

class Table(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[Any]]


class ToolCallInfo(BaseModel):
    tool: str
    arguments: dict


class ChatResponse(BaseModel):
    conversation_id: str
    answer: AgentAnswer | None
    tables: list[Table] = []
    data_sources: list[dict] = []
    tool_calls: list[ToolCallInfo] = []
    error: str | None = None


# ---------- JSON schema for OpenAI strict mode ----------

_KEEP = {"type", "properties", "required", "additionalProperties", "enum", "items", "anyOf",
         "description", "$ref", "$defs", "const"}


def _clean(node: Any) -> Any:
    if isinstance(node, list):
        return [_clean(v) for v in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key in ("properties", "$defs"):  # maps of name -> schema
            out[key] = {name: _clean(sub) for name, sub in value.items()}
        elif key in _KEEP:
            out[key] = _clean(value)
    if out.get("type") == "object":
        out.setdefault("properties", {})
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    return out


def openai_strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema reduced to what OpenAI strict mode accepts.

    Every property is required and additionalProperties is false; optional values are
    expressed as a union with null. Range and uniqueness limits are dropped here and
    enforced by Pydantic validation instead.
    """
    return _clean(model.model_json_schema())
