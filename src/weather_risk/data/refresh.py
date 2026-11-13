"""Fetch fresh data from the public sources into a snapshot directory.

Shared by `wra refresh` and the risk-change check (spec 002, FR-202), so both fetch the same way:
one source at a time, atomic writes, and a failed source keeps its previous data.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from weather_risk.data import sources, store
from weather_risk.hubs import load_hubs

SOURCES = ("weather", "nri", "all")


@dataclass
class RefreshResult:
    failures: list[str] = field(default_factory=list)  # e.g. "weather:dallas", "nri"


def fetch_all(root: Path, source: str = "all", echo: Callable[[str], None] = print,
              pause: Callable[[float], None] = time.sleep) -> RefreshResult:
    """Fetch `source` ("weather", "nri" or "all") into `root`, then mark the refresh complete."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    result = RefreshResult()

    if source in ("weather", "all"):
        for i, hub in enumerate(load_hubs()):
            if i:
                pause(3)  # stay under Open-Meteo's per-minute limit
            try:
                ds = sources.fetch_weather(hub)
                store.save_weather(root, ds)
                echo(f"weather  {hub.id:<13} ok   {len(ds.days)} days {ds.start_date}..{ds.end_date}")
            except Exception as exc:  # report and keep the previous file
                result.failures.append(f"weather:{hub.id}")
                echo(f"weather  {hub.id:<13} FAILED ({type(exc).__name__}: {exc}); previous data kept")

    if source in ("nri", "all"):
        try:
            nri = sources.fetch_nri()
            store.save_nri(root, nri)
            echo(f"nri      {len(nri.counties)} counties ok, version {nri.version}")
        except Exception as exc:
            result.failures.append("nri")
            echo(f"nri      FAILED ({type(exc).__name__}: {exc}); previous data kept")

    store.mark_refresh_complete(root, time.strftime("%Y-%m-%dT%H:%M:%S"))
    return result
