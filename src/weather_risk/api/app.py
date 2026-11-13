"""HTTP API (contracts/http-api.md). One FastAPI process serves the API and the chat page.

The LLM-free endpoints (/api/rankings, /api/hubs/{id}/breakdown) read the same engine the
agent's tools use, so the numbers are identical on every path (FR-029).
"""

import threading

from fastapi import FastAPI, HTTPException, Query

from weather_risk.data.store import snapshot_version
from weather_risk.hubs import Region
from weather_risk.scoring.engine import METRICS, OVERALL, Engine, UnknownHub, parse_metric
from weather_risk.settings import get_settings

app = FastAPI(title="Weather Risk Intelligence Agent", version="0.1.0")


class EngineHolder:
    """Builds the engine once and rebuilds it when a refresh rewrites a manifest (FR-008)."""

    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._version = -1.0
        self._lock = threading.Lock()

    def get(self) -> Engine:
        s = get_settings()
        version = snapshot_version(s.seed_dir, s.data_dir)
        with self._lock:
            if self._engine is None or version != self._version:
                self._engine = Engine.from_settings()
                self._version = version
            return self._engine


engines = EngineHolder()


@app.get("/api/health")
def health() -> dict:
    s = get_settings()
    sources = engines.get().data_sources()
    return {"status": "ok", "model": s.openai_model, "data_sources": sources}


@app.get("/api/hubs")
def hubs() -> list[dict]:
    return [
        {"id": h.id, "name": h.name, "region": h.region.value, "lat": h.lat, "lon": h.lon,
         "county_fips": h.county_fips}
        for h in engines.get().hubs.values()
    ]


@app.get("/api/rankings")
def rankings(
    hazard: str = Query(OVERALL, description=f"One of: {', '.join(METRICS)}"),
    region: Region | None = Query(None),
) -> dict:
    try:
        metric = parse_metric(hazard)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    engine = engines.get()
    return {
        "hazard": metric,
        "region": region.value if region else None,
        "rankings": [r.model_dump() for r in engine.rank_hubs(metric, region=region)],
        "data_sources": engine.data_sources(),
    }


@app.get("/api/hubs/{hub_id}/breakdown")
def hub_breakdown(hub_id: str) -> dict:
    engine = engines.get()
    try:
        b = engine.get_hub_breakdown(hub_id)
    except UnknownHub as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from None
    return {**b.model_dump(mode="json"), "data_sources": engine.data_sources()}
