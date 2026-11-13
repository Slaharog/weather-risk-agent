"""Allows `python -m weather_risk <command>`, equivalent to `wra <command>`.

Useful on machines where policy blocks the generated `wra.exe` launcher.
"""

from weather_risk.cli import app

app(prog_name="wra")
