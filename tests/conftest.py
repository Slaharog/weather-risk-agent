import pytest


@pytest.fixture(autouse=True)
def no_alert_secrets_from_dotenv(monkeypatch):
    """Settings also read the local .env. Blank the alert secrets so no test can ever POST to a
    real webhook or use a real admin token; tests that need them pass explicit values."""
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "")
    monkeypatch.setenv("ALERT_ADMIN_TOKEN", "")
