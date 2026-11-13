"""`wra alerts check|list` (spec 002, contracts/cli.md). Fake fetch: no network."""

import pytest
from typer.testing import CliRunner

from weather_risk.alerts import service
from weather_risk.cli import app
from weather_risk.data.refresh import RefreshResult

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setattr(service, "fetch_all", lambda root, source, echo: RefreshResult())


def test_list_with_no_checks():
    result = runner.invoke(app, ["alerts", "list"])
    assert result.exit_code == 0 and "No checks yet." in result.output


def test_first_check_records_a_baseline_then_list_shows_it():
    result = runner.invoke(app, ["alerts", "check"])
    assert result.exit_code == 0, result.output
    assert "16 hubs, 0 alerts" in result.output and "baseline recorded" in result.output
    listed = runner.invoke(app, ["alerts", "list"])
    assert "(manual)" in listed.output and "0 recent alerts." in listed.output


def test_fetch_failure_gives_exit_code_2(monkeypatch):
    monkeypatch.setattr(service, "fetch_all",
                        lambda root, source, echo: RefreshResult(failures=["nri"]))
    result = runner.invoke(app, ["alerts", "check"])
    assert result.exit_code == 2 and "fetch failures (previous data kept): nri" in result.output
