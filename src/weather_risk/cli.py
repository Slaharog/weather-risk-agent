"""Command line: `wra <command>` (or `python -m weather_risk.cli <command>`).

Exit codes: 0 success, 1 user error, 2 data or network failure.
"""

import sys
from enum import StrEnum

import typer

from weather_risk.data.refresh import fetch_all
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
    try:
        before = {h: s.score for h, s in Engine.from_settings().scores.items()}
    except FileNotFoundError:  # first ever fetch: nothing to compare with
        before = {}

    result = fetch_all(root, source.value, echo=lambda m: typer.echo(m, err="FAILED" in m))
    failures = len(result.failures)
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


@app.command(name="eval")
def eval_(
    model: str | None = typer.Option(None, help="Override OPENAI_MODEL for this run."),
    case: str | None = typer.Option(None, help="Run only this case id."),
    judge: bool = typer.Option(False, help="Add an LLM clarity score, reported separately."),
) -> None:
    """Run the eval set (evals/cases.yaml) against the live agent and report pass rates."""
    from evals.run import run

    summary = run(model=model, case_id=case, judge=judge)
    raise typer.Exit(code=0 if summary["passed"] == summary["cases"] else 1)


@app.command()
def serve(
    port: int = typer.Option(8000, envvar="PORT", help="Port (Railway sets PORT)."),
    host: str = typer.Option("127.0.0.1", envvar="HOST", help="Use 0.0.0.0 in a container."),
) -> None:
    """Start the API and the chat page."""
    import uvicorn

    typer.echo(f"Chat page: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
    uvicorn.run("weather_risk.api.app:app", host=host, port=port)


# ---------- risk-change alerts (spec 002, contracts/cli.md) ----------

alerts_app = typer.Typer(no_args_is_help=True, help="Risk-change alerts: check, demo, list.")
app.add_typer(alerts_app, name="alerts")


def _alert_line(a: dict) -> str:
    tag = "[demo] " if a["is_demo"] else ""
    name = a.get("hub_name", a["hub_id"])
    return (f"{tag}{name:<16} {a['metric']:<14} {a['old_value']:5.1f} -> {a['new_value']:5.1f}  "
            f"({a['change']:+.1f})   {a['delivery_status']}"
            + (f" ({a['delivery_error']})" if a.get("delivery_error") else ""))


def _print_summary(s) -> None:
    label = "Demo check" if s.kind == "demo" else f"Check ({s.kind})"
    note = ", baseline recorded" if s.baseline else ""
    typer.echo(f"{label} #{s.check_id}: {s.status}, {s.hubs_checked} hubs, {s.alerts_raised} alerts"
               f" (threshold {get_settings().alert_threshold}){note}")
    if s.fetch_failures:
        typer.echo("fetch failures (previous data kept): " + ", ".join(s.fetch_failures))
    for a in s.alerts:
        typer.echo(_alert_line(a))


@alerts_app.command("check")
def alerts_check() -> None:
    """Run a real check now: fetch live data into DATA_DIR, recompute, compare, alert."""
    import logging

    from weather_risk.alerts import service

    logging.basicConfig(level=logging.INFO, format="%(message)s")  # show fetch progress
    summary = service.run_check("manual")
    _print_summary(summary)
    if summary.status != "ok" or summary.fetch_failures:
        raise typer.Exit(code=2)


@alerts_app.command("list")
def alerts_list(limit: int = typer.Option(20, min=1, max=50, help="How many alerts to show.")) -> None:
    """Show the last check and the newest alerts. No LLM, no network."""
    from weather_risk.alerts.history import History

    history = History(get_settings().alerts_db)
    last = history.last_check()
    if last is None:
        typer.echo("No checks yet.")
    else:
        typer.echo(f"Last check #{last['id']} ({last['kind']}) at {last['started_at']}: {last['status']}, "
                   f"{last['hubs_checked']} hubs, {last['alerts_raised']} alerts")
    names = {h.id: h.name for h in load_hubs()}
    alerts = history.list_alerts(limit)
    typer.echo(f"{len(alerts)} recent alerts" + (":" if alerts else "."))
    for a in alerts:
        named = {**a, "hub_name": names.get(a["hub_id"], a["hub_id"])}
        typer.echo(f"{a['detected_at']}  " + _alert_line(named))


if __name__ == "__main__":
    app()
