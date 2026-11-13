"""HTTP API (contracts/http-api.md). One FastAPI process serves the API and the chat page.

The LLM-free endpoints (/api/rankings, /api/hubs/{id}/breakdown) read the same engine the
agent's tools use, so the numbers are identical on every path (FR-029).
"""

import asyncio
import threading
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from weather_risk.agent.conversations import ConversationStore
from weather_risk.agent.llm import LlmClient, LlmUnavailable, OpenAILlm
from weather_risk.agent.loop import run_turn
from weather_risk.agent.schemas import ChatResponse
from weather_risk.agent.tools import ToolRegistry
from weather_risk.alerts.scheduler import run_scheduler
from weather_risk.api.limits import RateLimiter
from weather_risk.data.store import snapshot_version
from weather_risk.hubs import Region
from weather_risk.scoring.engine import METRICS, OVERALL, Engine, UnknownHub, parse_metric
from weather_risk.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts the risk-change scheduler (spec 002) when ALERT_INTERVAL_HOURS > 0; off by default."""
    task = asyncio.create_task(run_scheduler()) if get_settings().alert_interval_hours > 0 else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Weather Risk Intelligence Agent", version="0.1.0", lifespan=lifespan)


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
MAX_CHAT_BODY_BYTES = 16_384  # far above a 1,000-character message plus a conversation id
STATIC_DIR = Path(__file__).parent / "static"
conversations = ConversationStore()
limiter = RateLimiter(get_settings().chat_per_minute, get_settings().chat_per_day)
TRUSTED_IP_HEADER = get_settings().trusted_ip_header


def client_ip(http: Request) -> str:
    """The client the rate limit applies to: the proxy's header if one is trusted, else the socket."""
    if TRUSTED_IP_HEADER and (forwarded := http.headers.get(TRUSTED_IP_HEADER)):
        return forwarded.strip()
    return http.client.host if http.client else "unknown"


@app.middleware("http")
async def limit_chat_body(request: Request, call_next):
    """Reject oversized chat bodies before they are read and parsed."""
    if request.url.path == "/api/chat":
        size = request.headers.get("content-length")
        if size is None or not size.isdigit() or int(size) > MAX_CHAT_BODY_BYTES:
            return JSONResponse({"detail": "Request body missing or too large."}, status_code=413)
    return await call_next(request)
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
def chat(request: ChatRequest, http: Request) -> ChatResponse:
    if not limiter.allow(client_ip(http)):
        raise HTTPException(status_code=429, detail="Too many questions right now. Please wait a minute.")
    try:
        llm = get_llm()
    except LlmUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Chat is not configured: {exc}") from None
    convo = conversations.get_or_create(request.conversation_id)
    with convo.lock:  # one turn at a time per conversation
        response = run_turn(convo, request.message, llm, ToolRegistry(engines.get()))
        conversations.save(convo)
    return response


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
