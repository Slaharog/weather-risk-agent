"""The agent's tools: a fixed allow-list of read-only calls into the scoring engine.

Each tool returns:
- `result`: JSON sent to the model (numbers rounded exactly as the user sees them),
- `table`: the numbers the user sees, built by code from the same engine output,
- `sources`: data provenance, attached to the answer by code.
The model never formats or produces a number the user sees (constitution Principle I).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from weather_risk.agent.schemas import (
    CoverageArgs,
    Table,
    openai_strict_schema,
)
from weather_risk.hubs import Region
from weather_risk.scoring.engine import Engine, UnknownHub
from weather_risk.scoring.stats import FIRST_YEAR, LAST_YEAR, STATS

HAZARD_DEFINITIONS = {
    "winter": "snow, ice storms, and extreme cold",
    "heat": "heat waves and days at or above 35 °C",
    "flood": "inland (river) and coastal flooding, and very heavy rain days",
    "hurricane": "hurricanes and tropical storms",
    "severe_storms": "tornadoes, hail, and strong wind",
}


def r1(x: float) -> float:
    """Display rounding. The model sees the same rounded values as the user's tables."""
    return round(x, 1)


@dataclass
class ToolOutcome:
    ok: bool
    tool: str
    arguments: dict
    result: dict
    table: Table | None = None
    sources: list[dict] = field(default_factory=list)
    missing_data: bool = False

    @classmethod
    def failure(cls, tool: str, message: str, arguments: dict | None = None) -> "ToolOutcome":
        return cls(ok=False, tool=tool, arguments=arguments or {}, result={"error": message})


@dataclass(frozen=True)
class ToolDef:
    args: type[BaseModel]
    description: str
    run: Callable[["ToolRegistry", BaseModel], ToolOutcome]


class ToolRegistry:
    def __init__(self, engine: Engine):
        self.engine = engine

    # ---------- plumbing ----------

    def specs(self) -> list[dict]:
        return [{"type": "function", "name": name, "description": d.description, "strict": True,
                 "parameters": openai_strict_schema(d.args)} for name, d in TOOLS.items()]

    def execute(self, name: str, arguments: str) -> ToolOutcome:
        if name not in TOOLS:
            return ToolOutcome.failure(name, f"Unknown tool '{name}'. Allowed: {', '.join(TOOLS)}.")
        tool = TOOLS[name]
        try:
            raw = json.loads(arguments or "{}")
            args = tool.args.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            msg = exc.errors(include_url=False) if isinstance(exc, ValidationError) else str(exc)
            return ToolOutcome.failure(name, f"Invalid arguments: {msg}")
        try:
            return tool.run(self, args)
        except (UnknownHub, ValueError) as exc:
            return ToolOutcome.failure(name, str(exc.args[0]), raw)

    def _outcome(self, name: str, args: BaseModel, data, table: Table, notes: list[str],
                 missing: bool = False) -> ToolOutcome:
        sources = self.engine.data_sources()
        return ToolOutcome(ok=True, tool=name, arguments=args.model_dump(mode="json"),
                           result={"data": data, "notes": notes, "sources": sources},
                           table=table, sources=sources, missing_data=missing)

    # ---------- tools ----------

    def list_coverage(self, args: CoverageArgs) -> ToolOutcome:
        hubs = [{"id": h.id, "name": h.name, "region": h.region.value}
                for h in self.engine.hubs.values()]
        data = {
            "hubs": hubs,
            "regions": {r.value: [h["id"] for h in hubs if h["region"] == r.value] for r in Region},
            "hazards": HAZARD_DEFINITIONS,
            "statistics": {name: s.definition for name, s in STATS.items()},
            "statistics_years": f"{FIRST_YEAR}-{LAST_YEAR} (last year = {LAST_YEAR})",
            "scores": "0-100 exposure scores; 'overall' = average of the five hazards",
        }
        table = Table(title="Hubs covered", columns=["Hub", "Region"],
                      rows=[[h["name"], h["region"]] for h in hubs])
        return self._outcome("list_coverage", args, data, table, [])


TOOLS: dict[str, ToolDef] = {
    "list_coverage": ToolDef(
        CoverageArgs,
        "List the hubs, regions, hazards, statistics and data period this system covers. "
        "Use it when the user asks what is covered, or names a city, region, hazard or "
        "period you cannot map to the other tools' arguments.",
        ToolRegistry.list_coverage,
    ),
}
