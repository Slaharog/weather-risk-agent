"""Alert settings validation (security review, T221)."""

import pytest
from pydantic import ValidationError

from weather_risk.settings import Settings


def test_admin_token_must_be_at_least_32_characters():
    with pytest.raises(ValidationError):
        Settings(alert_admin_token="too-short")
    assert Settings(alert_admin_token="x" * 32).alert_admin_token is not None


@pytest.mark.parametrize("url", ["http://hooks.example.test/x", "ftp://x", "hooks.example.test/x"])
def test_webhook_must_be_https(url):
    with pytest.raises(ValidationError) as exc:
        Settings(alert_webhook_url=url)
    assert "hooks.example.test/x" not in str(exc.value)  # the URL is not echoed in the error


@pytest.mark.parametrize("url", ["https://webhook.site/abc", "http://localhost:9000/hook",
                                 "http://127.0.0.1:9000/hook"])
def test_https_or_local_webhook_is_accepted(url):
    assert Settings(alert_webhook_url=url).alert_webhook_url is not None
