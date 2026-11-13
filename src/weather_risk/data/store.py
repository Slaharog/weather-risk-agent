"""Read and write the data snapshot as JSON files.

Layout of a snapshot directory (the committed seed, or the refreshed live directory):
    weather/<hub_id>.json   one WeatherDataset per hub
    nri_counties.json       NriDataset with all US counties
    manifest.json           human-readable summary: retrieval dates, NRI version, window

Writes are atomic: data goes to a temporary file that is renamed into place only after
it was written completely, so a failed refresh never leaves a half-written file.
"""

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from weather_risk.data.models import NriDataset, WeatherDataset


@dataclass(frozen=True)
class Snapshot:
    weather: dict[str, WeatherDataset]
    nri: NriDataset


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _update_manifest(root: Path, section: str, key: str | None, value: dict) -> None:
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if key is None:
        manifest[section] = value
    else:
        manifest.setdefault(section, {})[key] = value
    _atomic_write(path, json.dumps(manifest, indent=2, sort_keys=True))


def save_weather(root: Path, ds: WeatherDataset) -> None:
    text = ds.model_dump_json()
    WeatherDataset.model_validate_json(text)  # never write something we cannot read back
    _atomic_write(root / "weather" / f"{ds.hub_id}.json", text)
    _update_manifest(root, "weather", ds.hub_id, {
        "source": ds.source,
        "start_date": ds.start_date.isoformat(),
        "end_date": ds.end_date.isoformat(),
        "retrieved_at": ds.retrieved_at,
        "days": len(ds.days),
    })


def save_nri(root: Path, ds: NriDataset) -> None:
    text = ds.model_dump_json()
    NriDataset.model_validate_json(text)
    _atomic_write(root / "nri_counties.json", text)
    _update_manifest(root, "nri", None, {
        "source": ds.source,
        "version": ds.version,
        "retrieved_at": ds.retrieved_at,
        "counties": len(ds.counties),
    })


def _pick(relative: str, data_dir: Path, seed_dir: Path) -> Path:
    """The refreshed (live) file wins over the committed seed, per file."""
    live = data_dir / relative
    return live if live.exists() else seed_dir / relative


def load_snapshot(seed_dir: Path, data_dir: Path, hub_ids: Iterable[str]) -> Snapshot:
    weather = {
        hub_id: WeatherDataset.model_validate_json(
            _pick(f"weather/{hub_id}.json", data_dir, seed_dir).read_text(encoding="utf-8")
        )
        for hub_id in hub_ids
    }
    nri = NriDataset.model_validate_json(
        _pick("nri_counties.json", data_dir, seed_dir).read_text(encoding="utf-8")
    )
    return Snapshot(weather=weather, nri=nri)


COMPLETE_MARKER = "refresh_complete.txt"


def mark_refresh_complete(root: Path, when: str) -> None:
    """Written once at the END of `wra refresh`, after every source was saved."""
    _atomic_write(root / COMPLETE_MARKER, when)


def snapshot_version(seed_dir: Path, data_dir: Path) -> float:
    """Changes only when a refresh has finished, so the server never loads a half-done refresh."""
    paths = [seed_dir / COMPLETE_MARKER, data_dir / COMPLETE_MARKER]
    return max((p.stat().st_mtime for p in paths if p.exists()), default=0.0)
