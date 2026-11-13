"""Command line: `wra <command>` (or `python -m weather_risk.cli <command>`).

Exit codes: 0 success, 1 user error, 2 data or network failure.
"""

import time
from enum import StrEnum

import typer

from weather_risk.data import sources, store
from weather_risk.hubs import load_hubs
from weather_risk.settings import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Weather Risk Intelligence Agent")


@app.callback()
def main() -> None:
    """Weather Risk Intelligence Agent."""


class Source(StrEnum):
    WEATHER = "weather"
    NRI = "nri"
    ALL = "all"


class Target(StrEnum):
    LIVE = "live"
    SEED = "seed"


@app.command()
def refresh(
    source: Source = typer.Option(Source.ALL, help="Which source to fetch."),
    to: Target = typer.Option(Target.LIVE, help="live = DATA_DIR; seed = the committed snapshot."),
) -> None:
    """Fetch fresh data from Open-Meteo and FEMA NRI. A failed source keeps its previous data."""
    settings = get_settings()
    root = settings.data_dir if to == Target.LIVE else settings.seed_dir
    failures = 0

    if source in (Source.WEATHER, Source.ALL):
        for i, hub in enumerate(load_hubs()):
            if i:
                time.sleep(3)  # stay under Open-Meteo's per-minute limit
            try:
                ds = sources.fetch_weather(hub)
                store.save_weather(root, ds)
                typer.echo(f"weather  {hub.id:<13} ok   {len(ds.days)} days "
                           f"{ds.start_date}..{ds.end_date}")
            except Exception as exc:  # report and keep the previous file
                failures += 1
                typer.echo(f"weather  {hub.id:<13} FAILED ({exc}); previous data kept", err=True)

    if source in (Source.NRI, Source.ALL):
        try:
            nri = sources.fetch_nri()
            store.save_nri(root, nri)
            typer.echo(f"nri      {len(nri.counties)} counties ok, version {nri.version}")
        except Exception as exc:
            failures += 1
            typer.echo(f"nri      FAILED ({exc}); previous data kept", err=True)

    typer.echo(f"written to {root}")
    if failures:
        raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
