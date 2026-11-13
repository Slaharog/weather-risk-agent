"""Runtime configuration, read from environment variables or a local .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # Only chat and evals need the key; the scoring engine, CLI and LLM-free API work without it.
    openai_api_key: str | None = None
    openai_model: str = "gpt-6.1-sol"
    openai_reasoning_effort: str = "low"

    # Budget protection for /api/chat once public (per client per minute, all clients per day).
    chat_per_minute: int = 10
    chat_per_day: int = 500
    # Header a trusted reverse proxy uses for the client IP (Railway: X-Real-IP). Unset locally,
    # because without a proxy in front, any client could set the header to dodge the limit.
    trusted_ip_header: str | None = None

    # Refreshed data goes to data_dir; the committed snapshot lives in seed_dir.
    data_dir: Path = PROJECT_ROOT / "data" / "live"
    seed_dir: Path = PROJECT_ROOT / "data" / "seed"
    hubs_file: Path = PROJECT_ROOT / "config" / "hubs.toml"


def get_settings() -> Settings:
    return Settings()
