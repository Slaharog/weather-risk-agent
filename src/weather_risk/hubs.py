"""The fixed hub list and US Census regions, loaded from config/hubs.toml."""

import tomllib
from enum import StrEnum
from functools import cache
from pathlib import Path

from pydantic import BaseModel

from weather_risk.settings import get_settings


class Region(StrEnum):
    MIDWEST = "Midwest"
    SOUTH = "South"
    WEST = "West"
    NORTHEAST = "Northeast"


class Hub(BaseModel):
    id: str
    name: str
    city: str
    state: str
    lat: float
    lon: float
    county_fips: str
    timezone: str
    region: Region


@cache
def _load(path: Path) -> tuple[Hub, ...]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    state_to_region = {
        state: Region(region) for region, states in raw["regions"].items() for state in states
    }
    return tuple(Hub(**h, region=state_to_region[h["state"]]) for h in raw["hubs"])


def load_hubs() -> tuple[Hub, ...]:
    return _load(get_settings().hubs_file)


def get_hub(hub_id: str) -> Hub:
    for hub in load_hubs():
        if hub.id == hub_id:
            return hub
    raise KeyError(f"Unknown hub: {hub_id}")


def hubs_in_region(region: Region) -> list[Hub]:
    return [h for h in load_hubs() if h.region == region]
