"""Raw source data as stored in the snapshot (see data-model.md section 2)."""

from datetime import date

from pydantic import BaseModel

# FEMA National Risk Index hazard codes we use (December 2025 release).
# IFLD = inland (riverine) flooding; older releases called it RFLD.
NRI_HAZARD_CODES = ("HRCN", "IFLD", "CFLD", "WNTW", "ISTM", "CWAV", "HWAV", "TRND", "HAIL", "SWND")

WEATHER_SOURCE = "Open-Meteo Historical Weather API (ERA5)"
NRI_SOURCE = "FEMA National Risk Index"


class DailyWeather(BaseModel):
    date: date
    snowfall_cm: float | None
    precipitation_mm: float | None
    tmax_c: float | None
    tmin_c: float | None
    gust_max_kmh: float | None


class WeatherDataset(BaseModel):
    hub_id: str
    source: str = WEATHER_SOURCE
    start_date: date
    end_date: date
    retrieved_at: str
    days: list[DailyWeather]


class NriCounty(BaseModel):
    fips: str
    county: str
    state: str
    # Annualized frequency (expected events per year) per hazard code; None = not applicable.
    afreq: dict[str, float | None]


class NriDataset(BaseModel):
    source: str = NRI_SOURCE
    version: str
    retrieved_at: str
    counties: list[NriCounty]
