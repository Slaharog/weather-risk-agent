"""Runtime configuration, read from environment variables or a local .env file."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
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

    # Risk-change alerts (spec 002). 0 hours = scheduler off: local runs and evals never fetch
    # live data by surprise; Railway sets 24. The webhook URL and admin token are secrets: they
    # come only from the environment and are never logged or returned (Principle VII).
    alert_interval_hours: float = Field(0, ge=0)
    alert_threshold: float = Field(2.0, gt=0)
    alert_webhook_url: SecretStr | None = None
    alert_admin_token: SecretStr | None = None

    @field_validator("alert_webhook_url", "alert_admin_token", mode="before")
    @classmethod
    def _blank_is_unset(cls, value):
        # An empty variable (e.g. ALERT_WEBHOOK_URL= in .env) means "not configured".
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def alerts_db(self) -> Path:
        return self.data_dir / "alerts.sqlite"


def get_settings() -> Settings:
    return Settings()
