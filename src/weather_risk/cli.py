"""Command line: `wra <command>` (or `python -m weather_risk.cli <command>`).

Exit codes: 0 success, 1 user error, 2 data or network failure.
"""

import sys
import time
from enum import StrEnum

import typer

from weather_risk.data import sources, store
from weather_risk.hubs import Region, load_hubs
from weather_risk.scoring.engine import METRICS, Engine, UnknownHub, parse_metric
from weather_risk.settings import get_settings

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Weather Risk Intelligence Agent")


@app.callback()
def main() -> None:
    """Weather Risk Intelligence Agent."""
    # Windows consoles default to a legacy code page; print units like °C correctly.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


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
    try:
        before = {h: s.score for h, s in Engine.from_settings().scores.items()}
    except FileNotFoundError:  # first ever fetch: nothing to compare with
        before = {}

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

    typer.echo(f"written to {root}\n")
    try:
        engine = Engine.from_settings()
    except FileNotFoundError:
        typer.echo("Snapshot incomplete; cannot recompute scores yet.", err=True)
        raise typer.Exit(code=2) from None
    _print_ranking(engine, "overall", engine.rank_hubs("overall"))
    changed = [(h, before[h], s.score) for h, s in engine.scores.items()
               if h in before and abs(before[h] - s.score) >= 0.05]
    typer.echo("\nChanged overall scores: " + (", ".join(
        f"{h} {old:.1f} -> {new:.1f}" for h, old, new in changed) if changed else "none"))
    if failures:
        raise typer.Exit(code=2)


# ---------- LLM-free views of the engine (FR-029) ----------

def _print_ranking(engine: Engine, metric: str, rows) -> None:
    typer.echo(f"{'Rank':<5}{'Hub':<18}{'Region':<11}{metric + ' score':>16}  Top drivers")
    for r in rows:
        drivers = "; ".join(f"{d.label.split(' (')[0]} +{d.contribution:.1f}" for d in r.top_drivers)
        tie = "=" if r.tied else " "
        typer.echo(f"{r.rank:<4}{tie}{r.name:<18}{r.region:<11}{r.score:>16.1f}  {drivers}")
    _print_sources(engine)


def _print_sources(engine: Engine) -> None:
    typer.echo("\nSources: " + " | ".join(
        f"{s['name']}, {s['period']} (retrieved {s['retrieved_at']})" for s in engine.data_sources()))


@app.command()
def rank(
    hazard: str = typer.Option("overall", help=f"One of: {', '.join(METRICS)}"),
    region: Region | None = typer.Option(None, help="Filter to one US Census region."),
) -> None:
    """Rank hubs by overall or per-hazard exposure score. No LLM involved."""
    try:
        metric = parse_metric(hazard)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    engine = Engine.from_settings()
    _print_ranking(engine, metric, engine.rank_hubs(metric, region=region))


@app.command()
def breakdown(hub_id: str = typer.Argument(..., help="Hub id, e.g. dallas")) -> None:
    """Show everything behind a hub's score. No LLM involved."""
    engine = Engine.from_settings()
    try:
        b = engine.get_hub_breakdown(hub_id)
    except UnknownHub as exc:
        typer.echo(exc.args[0], err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"{b.name} ({b.region}): overall {b.overall_score:.1f}, "
               f"rank {b.overall_rank} of {b.hub_count}\n")
    for h in b.hazards:
        typer.echo(f"{h.hazard.value:<14} {h.score:5.1f}   rank {h.rank:>2} of {b.hub_count}")
        for c in h.components:
            typer.echo(f"    {c.weight:4.2f} x {c.indicator_score:5.1f} = {c.contribution:5.1f}   "
                       f"{c.label}: {c.raw_value:.3g} {c.raw_unit}")
        if h.missing:
            typer.echo(f"    missing (weights re-normalized): {', '.join(h.missing)}")
    _print_sources(engine)


@app.command()
def stat(
    hub_id: str = typer.Argument(..., help="Hub id, e.g. denver"),
    name: str = typer.Argument(..., help="Statistic, e.g. snowfall_days_pct"),
    year: int = typer.Option(2025, help="Calendar year, 2016-2025 ('last year' = 2025)."),
) -> None:
    """One weather statistic for a hub and year, with the counts behind it. No LLM involved."""
    engine = Engine.from_settings()
    try:
        s = engine.weather_stat(hub_id, name, year)
    except (UnknownHub, ValueError) as exc:
        typer.echo(exc.args[0], err=True)
        raise typer.Exit(code=1) from None
    hub = engine.hubs[hub_id].name
    typer.echo(f"{hub}, {s.period_start} to {s.period_end}: {name} = {s.value:.1f} {s.unit}")
    if s.qualifying_days is not None:
        typer.echo(f"  qualifying days: {s.qualifying_days}")
    typer.echo(f"  days with data: {s.days_with_data}, missing days: {s.missing_days}")
    typer.echo(f"  definition: {s.definition}")
    _print_sources(engine)


@app.command()
def serve(
    port: int = typer.Option(8000, envvar="PORT", help="Port (Railway sets PORT)."),
    host: str = typer.Option("127.0.0.1", envvar="HOST", help="Use 0.0.0.0 in a container."),
) -> None:
    """Start the API and the chat page."""
    import uvicorn

    typer.echo(f"Chat page: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
    uvicorn.run("weather_risk.api.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
