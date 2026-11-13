from typer.testing import CliRunner

from weather_risk.cli import app

runner = CliRunner()


def test_rank_runs_and_is_deterministic():
    first = runner.invoke(app, ["rank", "--hazard", "winter", "--region", "Midwest"])
    second = runner.invoke(app, ["rank", "--hazard", "winter", "--region", "Midwest"])
    assert first.exit_code == 0
    assert first.output == second.output
    assert "Minneapolis" in first.output


def test_rank_unknown_hazard_is_a_user_error():
    result = runner.invoke(app, ["rank", "--hazard", "earthquake"])
    assert result.exit_code == 1
