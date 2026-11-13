"""HTTP API (contracts/http-api.md). One FastAPI process serves the API and the chat page.

The LLM-free endpoints (/api/rankings, /api/hubs/{id}/breakdown) read the same engine the
agent's tools use, so the numbers are identical on every path (FR-029).
"""

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from weather_risk.agent.conversations import ConversationStore
from weather_risk.agent.llm import LlmClient, LlmUnavailable, OpenAILlm
from weather_risk.agent.loop import run_turn
from weather_risk.agent.schemas import ChatResponse
from weather_risk.agent.tools import ToolRegistry
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


# ---------- chat (the agent) ----------

MAX_MESSAGE_CHARS = 1000
STATIC_DIR = Path(__file__).parent / "static"
conversations = ConversationStore()
_llm: LlmClient | None = None


def get_llm() -> LlmClient:
    """Created on first use; raises LlmUnavailable when no API key is configured."""
    global _llm
    if _llm is None:
        _llm = OpenAILlm()
    return _llm


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(description=f"1 to {MAX_MESSAGE_CHARS} characters.")

    @field_validator("message")
    @classmethod
    def _length(cls, value: str) -> str:
        value = value.strip()
        if not 1 <= len(value) <= MAX_MESSAGE_CHARS:
            raise ValueError(f"message must be 1 to {MAX_MESSAGE_CHARS} characters")
        return value


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        llm = get_llm()
    except LlmUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Chat is not configured: {exc}") from None
    convo = conversations.get_or_create(request.conversation_id)
    response = run_turn(convo, request.message, llm, ToolRegistry(engines.get()))
    conversations.save(convo)
    return response


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
