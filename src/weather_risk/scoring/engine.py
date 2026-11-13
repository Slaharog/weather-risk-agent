"""The deterministic scoring engine (data-model.md sections 4-5).

Every score is a transparent weighted sum of indicators, and every component is kept,
so any number can be explained and recomputed. No LLM is involved anywhere in this module.
"""

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel

from weather_risk.data.models import NRI_SOURCE, WEATHER_SOURCE, DailyWeather, NriCounty
from weather_risk.data.store import Snapshot
from weather_risk.hubs import Hub
from weather_risk.scoring.indicators import (
    OBSERVED_INDICATORS,
    annual_rate,
    fema_ratio,
    national_p99,
    observed_score,
)


class Hazard(StrEnum):
    WINTER = "winter"
    HEAT = "heat"
    FLOOD = "flood"
    HURRICANE = "hurricane"
    SEVERE_STORMS = "severe_storms"


# Indicator weights per hazard. Each row sums to 1.0. These are documented judgment calls:
# each hazard leans on the source that measures it best (see docs/decisions.md).
HAZARD_WEIGHTS: dict[Hazard, dict[str, float]] = {
    Hazard.WINTER: {"fema_WNTW": 0.25, "fema_ISTM": 0.15, "fema_CWAV": 0.10,
                    "heavy_snow_days": 0.25, "severe_cold_days": 0.25},
    Hazard.HEAT: {"fema_HWAV": 0.50, "extreme_heat_days": 0.50},
    Hazard.FLOOD: {"fema_flood": 0.70, "heavy_rain_days": 0.30},
    Hazard.HURRICANE: {"fema_HRCN": 1.00},
    Hazard.SEVERE_STORMS: {"fema_TRND": 0.30, "fema_HAIL": 0.25, "fema_SWND": 0.25,
                           "high_wind_days": 0.20},
}

NRI_LABELS = {
    "WNTW": "winter weather", "ISTM": "ice storm", "CWAV": "cold wave", "HWAV": "heat wave",
    "HRCN": "hurricane", "TRND": "tornado", "HAIL": "hail", "SWND": "strong wind",
    "IFLD": "inland flooding", "CFLD": "coastal flooding",
}


class IndicatorValue(BaseModel):
    score: float  # 0-100
    raw_value: float
    raw_unit: str  # "events/yr" or "days/yr"
    source: str
    label: str = ""


class Component(BaseModel):
    indicator: str
    label: str
    weight: float  # after re-normalization if something was missing
    indicator_score: float
    contribution: float  # weight * indicator_score
    raw_value: float
    raw_unit: str
    source: str


class HazardScore(BaseModel):
    hub_id: str
    hazard: Hazard
    score: float
    components: list[Component]
    missing: list[str]


class OverallScore(BaseModel):
    hub_id: str
    score: float
    hazards: dict[Hazard, HazardScore]


# ---------- indicators for one hub ----------

def _fema(code: str, county: NriCounty, population: Sequence[NriCounty]) -> IndicatorValue:
    value = county.afreq.get(code)
    p99 = national_p99([c.afreq.get(code) for c in population])
    return IndicatorValue(
        score=fema_ratio(value, p99),
        raw_value=value or 0.0,
        raw_unit="events/yr",
        source=NRI_SOURCE,
        label=f"FEMA {NRI_LABELS[code]} events per year (100 = 99th-percentile US county, "
              f"{p99:.3g}/yr)",
    )


def indicator_values(
    county: NriCounty, population: Sequence[NriCounty], days: Sequence[DailyWeather]
) -> dict[str, IndicatorValue | None]:
    values: dict[str, IndicatorValue | None] = {}
    for code in ("WNTW", "ISTM", "CWAV", "HWAV", "HRCN", "TRND", "HAIL", "SWND"):
        values[f"fema_{code}"] = _fema(code, county, population)

    # Flood: the worse of inland and coastal flooding (different mechanisms; a coastal hub
    # should not have its flood exposure diluted by low inland flooding).
    inland, coastal = _fema("IFLD", county, population), _fema("CFLD", county, population)
    values["fema_flood"] = coastal if coastal.score > inland.score else inland

    for name, ind in OBSERVED_INDICATORS.items():
        rate, days_with_data = annual_rate(days, ind)
        values[name] = None if days_with_data == 0 else IndicatorValue(
            score=observed_score(rate, ind.cap),
            raw_value=rate,
            raw_unit="days/yr",
            source=WEATHER_SOURCE,
            label=f"{ind.description} per year",
        )
    return values


# ---------- combining ----------

def combine(hub_id: str, hazard: Hazard, values: dict[str, IndicatorValue | None]) -> HazardScore:
    weights = HAZARD_WEIGHTS[hazard]
    present = {k: w for k, w in weights.items() if values.get(k) is not None}
    missing = [k for k in weights if k not in present]
    total_weight = sum(present.values())
    components = []
    for key, w in present.items():
        v = values[key]
        weight = w / total_weight  # re-normalize when something is missing
        components.append(Component(
            indicator=key, label=v.label or key, weight=weight, indicator_score=v.score,
            contribution=weight * v.score, raw_value=v.raw_value, raw_unit=v.raw_unit,
            source=v.source,
        ))
    return HazardScore(hub_id=hub_id, hazard=hazard, missing=missing, components=components,
                       score=sum(c.contribution for c in components))


def overall_score(hub_id: str, hazards: dict[Hazard, HazardScore]) -> OverallScore:
    return OverallScore(hub_id=hub_id, hazards=hazards,
                        score=sum(h.score for h in hazards.values()) / len(hazards))


# ---------- the engine ----------

class Engine:
    """All hub scores, computed once from a snapshot."""

    def __init__(self, hubs: Sequence[Hub], snapshot: Snapshot):
        self.hubs = {h.id: h for h in hubs}
        self.snapshot = snapshot
        counties = {c.fips: c for c in snapshot.nri.counties}
        self.scores: dict[str, OverallScore] = {}
        for hub in hubs:
            values = indicator_values(counties[hub.county_fips], snapshot.nri.counties,
                                      snapshot.weather[hub.id].days)
            hazards = {h: combine(hub.id, h, values) for h in Hazard}
            self.scores[hub.id] = overall_score(hub.id, hazards)

    @classmethod
    def from_settings(cls) -> "Engine":
        from weather_risk.data.store import load_snapshot
        from weather_risk.hubs import load_hubs
        from weather_risk.settings import get_settings

        s, hubs = get_settings(), load_hubs()
        return cls(hubs, load_snapshot(s.seed_dir, s.data_dir, [h.id for h in hubs]))

    def data_sources(self) -> list[dict]:
        weather = list(self.snapshot.weather.values())
        return [
            {"name": NRI_SOURCE, "period": f"{self.snapshot.nri.version} release",
             "retrieved_at": self.snapshot.nri.retrieved_at},
            {"name": WEATHER_SOURCE,
             "period": f"{min(w.start_date for w in weather)} to {max(w.end_date for w in weather)}",
             "retrieved_at": max(w.retrieved_at for w in weather)},
        ]
