"""Runtime configuration, read from environment variables or a local .env file."""

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # hide_input_in_errors: a bad value (e.g. a webhook URL or API key) is never echoed in an error.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore",
                                      hide_input_in_errors=True)

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

    @field_validator("alert_admin_token")
    @classmethod
    def _token_is_long(cls, value: SecretStr | None):
        # Security review: a short token could be guessed. secrets.token_urlsafe(32) gives 43.
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("ALERT_ADMIN_TOKEN must be at least 32 characters")
        return value

    @field_validator("alert_webhook_url")
    @classmethod
    def _webhook_is_https(cls, value: SecretStr | None):
        # Alerts leave the service, so require TLS (localhost allowed for testing). Validated
        # after SecretStr wrapping, so a validation error shows '**********', not the URL.
        if value is not None:
            url = value.get_secret_value()
            local = url.startswith(("http://localhost", "http://127.0.0.1"))
            if not (url.startswith("https://") or local):
                raise ValueError("ALERT_WEBHOOK_URL must start with https://")
        return value

    @property
    def alerts_db(self) -> Path:
        return self.data_dir / "alerts.sqlite"


def get_settings() -> Settings:
    return Settings()
