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
    BreakdownArgs,
    CompareArgs,
    CoverageArgs,
    RankArgs,
    StatArgs,
    Table,
    openai_strict_schema,
)
from weather_risk.hubs import Region
from weather_risk.scoring.engine import Component, Engine, UnknownHub
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


def raw(x: float) -> float:
    """Raw source values (events/yr, days/yr) to 3 significant figures, as displayed."""
    return float(f"{x:.3g}")


def _short(label: str) -> str:
    return label.split(" (")[0]


def _component(c: Component) -> dict:
    return {"indicator": _short(c.label), "raw_value": raw(c.raw_value), "unit": c.raw_unit,
            "indicator_score": r1(c.indicator_score), "weight": round(c.weight, 2),
            "contribution": r1(c.contribution)}


def _component_text(c: Component) -> str:
    return f"{_short(c.label)}: {raw(c.raw_value)} {c.raw_unit} (+{r1(c.contribution)})"


def _metric_name(metric: str) -> str:
    return metric.replace("_", " ")


@dataclass
class ToolOutcome:
    ok: bool
    tool: str
    arguments: dict
    result: dict
    table: Table | None = None
    sources: list[dict] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # e.g. "minneapolis: heavy_snow_days"

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
                 missing: list[str] | None = None) -> ToolOutcome:
        sources = self.engine.data_sources()
        return ToolOutcome(ok=True, tool=name, arguments=args.model_dump(mode="json"),
                           result={"data": data, "notes": notes, "sources": sources},
                           table=table, sources=sources, missing=missing or [])

    def _missing(self, hub_ids: list[str], metrics: list[str]) -> list[str]:
        """Missing score components, only for the hazards actually shown ('overall' = all five)."""
        out = []
        for hub_id in hub_ids:
            hazards = self.engine.scores[hub_id].hazards
            for h, hs in hazards.items():
                if "overall" in metrics or h.value in metrics:
                    out += [f"{hub_id}: {m}" for m in hs.missing]
        return sorted(set(out))

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

    def rank_hubs(self, args: RankArgs) -> ToolOutcome:
        e = self.engine
        rows = e.rank_hubs(args.hazard, region=args.region, limit=args.limit)
        data = [{"rank": r.rank, "hub_id": r.hub_id, "hub": r.name, "region": r.region,
                 "score": r1(r.score), "tied": r.tied,
                 "top_drivers": [{"driver": _short(d.label), "contribution": r1(d.contribution)}
                                 for d in r.top_drivers]} for r in rows]
        scope = f"{args.region.value} hubs" if args.region else "All hubs"
        table = Table(
            title=f"{scope} ranked by {_metric_name(args.hazard)} score (0-100)",
            columns=["Rank", "Hub", "Region", "Score", "Top drivers"],
            rows=[[d["rank"], d["hub"], d["region"], d["score"],
                   "; ".join(f"{t['driver']} +{t['contribution']}" for t in d["top_drivers"])]
                  for d in data])
        notes = ["Tied hubs share a score; order among them is alphabetical."] if any(
            r.tied for r in rows) else []
        missing = self._missing([r.hub_id for r in rows], [args.hazard])
        return self._outcome("rank_hubs", args, data, table, notes, missing)

    def get_hub_breakdown(self, args: BreakdownArgs) -> ToolOutcome:
        b = self.engine.get_hub_breakdown(args.hub_id.value)
        data = {
            "hub": b.name, "region": b.region, "overall_score": r1(b.overall_score),
            "overall_rank": b.overall_rank, "hub_count": b.hub_count,
            "hazards": [{"hazard": h.hazard.value, "score": r1(h.score), "rank": h.rank,
                         "components": [_component(c) for c in
                                        sorted(h.components, key=lambda c: -c.contribution)],
                         "missing": h.missing} for h in b.hazards],
        }
        table = Table(
            title=f"{b.name}: overall {r1(b.overall_score)}, rank {b.overall_rank} of {b.hub_count}",
            columns=["Hazard", "Score", "Rank", "Largest components"],
            rows=[[_metric_name(h.hazard.value), r1(h.score), h.rank, "; ".join(
                _component_text(c) for c in sorted(h.components, key=lambda c: -c.contribution)[:2])]
                for h in b.hazards])
        notes = ["Overall = average of the five hazard scores. Each hazard score = sum of its "
                 "components' contributions."]
        missing = self._missing([b.hub_id], ["overall"])
        return self._outcome("get_hub_breakdown", args, data, table, notes, missing)

    def compare_hubs(self, args: CompareArgs) -> ToolOutcome:
        e = self.engine
        c = e.compare_hubs([h.value for h in args.hub_ids], list(args.hazards))
        names = {r.hub_id: r.name for r in c.rows}
        data = {
            "metrics": c.metrics,
            "hubs": [{"hub": r.name, "scores": {
                m: {"score": r1(cell.score), "components": [_component(x) for x in sorted(
                    cell.components, key=lambda x: -x.contribution)[:3]]}
                for m, cell in r.scores.items()}} for r in c.rows],
            "most_exposed": {m: names.get(h, "tie") for m, h in c.most_exposed.items()},
        }
        table = Table(
            title="Comparison (scores 0-100)",
            columns=["Hazard", *[r.name for r in c.rows], "Most exposed"],
            rows=[[_metric_name(m), *[r1(r.scores[m].score) for r in c.rows],
                   names.get(c.most_exposed[m], "tie")] for m in c.metrics])
        missing = self._missing([r.hub_id for r in c.rows], c.metrics)
        return self._outcome("compare_hubs", args, data, table, [], missing)

    def get_weather_stat(self, args: StatArgs) -> ToolOutcome:
        hub = self.engine.hubs[args.hub_id.value]
        s = self.engine.weather_stat(hub.id, args.stat.value, args.year)
        data = {"hub": hub.name, "statistic": s.stat, "value": r1(s.value), "unit": s.unit,
                "period": f"{s.period_start} to {s.period_end}",
                "qualifying_days": s.qualifying_days, "days_with_data": s.days_with_data,
                "missing_days": s.missing_days, "definition": s.definition}
        table = Table(
            title=f"{hub.name}, {args.year}: {_metric_name(s.stat)}",
            columns=["Value", "Unit", "Qualifying days", "Days with data", "Missing days", "Definition"],
            rows=[[r1(s.value), s.unit, "-" if s.qualifying_days is None else s.qualifying_days,
                   s.days_with_data, s.missing_days, s.definition]])
        notes = ["Source: ERA5 reanalysis at about 25 km resolution; values are grid estimates, "
                 "not station readings."]
        missing = [f"{hub.id}: {s.missing_days} days without data in {args.year}"] if s.missing_days else []
        return self._outcome("get_weather_stat", args, data, table, notes, missing)


TOOLS: dict[str, ToolDef] = {
    "rank_hubs": ToolDef(
        RankArgs,
        "Rank hubs by exposure score (0-100) for one hazard or 'overall', optionally within one "
        "US Census region. Returns ranks, scores and the two largest drivers per hub.",
        ToolRegistry.rank_hubs,
    ),
    "get_hub_breakdown": ToolDef(
        BreakdownArgs,
        "Everything behind one hub's score: overall score and rank, each hazard's score and "
        "rank, and every component with its raw value. Use for 'why is X high/low' questions.",
        ToolRegistry.get_hub_breakdown,
    ),
    "compare_hubs": ToolDef(
        CompareArgs,
        "Compare 2-6 hubs on 1-6 hazards (or 'overall'): scores, main components, and which "
        "hub is most exposed per hazard.",
        ToolRegistry.compare_hubs,
    ),
    "get_weather_stat": ToolDef(
        StatArgs,
        "One observed weather statistic for one hub and one calendar year (2016-2025), with the "
        "counts behind it. Example: snowfall_days_pct for denver in 2025.",
        ToolRegistry.get_weather_stat,
    ),
    "list_coverage": ToolDef(
        CoverageArgs,
        "List the hubs, regions, hazards, statistics and data period this system covers. "
        "Use it when the user asks what is covered, or names a city, region, hazard or "
        "period you cannot map to the other tools' arguments.",
        ToolRegistry.list_coverage,
    ),
}
