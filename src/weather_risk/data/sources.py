"""Fetch raw data from the two public sources. Used only by `wra refresh`.

The app itself never calls these APIs while answering questions; it reads the snapshot.
"""

import ssl
import time
from datetime import UTC, date, datetime

import httpx

from weather_risk.data.models import (
    NRI_HAZARD_CODES,
    DailyWeather,
    NriCounty,
    NriDataset,
    WeatherDataset,
)
from weather_risk.hubs import Hub

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
NRI_URL = (
    "https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/"
    "National_Risk_Index_Counties/FeatureServer/0/query"
)
WINDOW_START = date(2016, 1, 1)
WINDOW_END = date(2025, 12, 31)
DAILY_VARS = "snowfall_sum,precipitation_sum,temperature_2m_max,temperature_2m_min,wind_gusts_10m_max"
NRI_PAGE_SIZE = 2000


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _client() -> httpx.Client:
    # Use the operating system's certificate store, so TLS works behind corporate
    # proxies or antivirus that re-sign certificates.
    return httpx.Client(
        verify=ssl.create_default_context(),
        timeout=60,
        headers={"User-Agent": "weather-risk-agent (interview project)"},
    )


RATE_LIMIT_WAIT_S = 60  # Open-Meteo weights long multi-variable requests as many calls


class SourceError(RuntimeError):
    """A public data source failed; the message is short and safe to print."""


def _get_json(client: httpx.Client, url: str, params: dict, retries: int = 3) -> dict:
    for attempt in range(retries + 1):
        try:
            response = client.get(url, params=params)
            if response.status_code == 429 and attempt < retries:
                time.sleep(RATE_LIMIT_WAIT_S)
                continue
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise SourceError(f"HTTP {exc.response.status_code} from {exc.request.url.host}") from exc
        except (httpx.TransportError, ValueError) as exc:
            if attempt == retries:
                raise SourceError(f"{type(exc).__name__} calling {url.split('/')[2]}") from exc
            time.sleep(2 * (attempt + 1))
    raise SourceError(f"still rate-limited by {url.split('/')[2]} after {retries} retries")


# ---------- Open-Meteo ----------

def parse_open_meteo(hub_id: str, payload: dict, retrieved_at: str) -> WeatherDataset:
    daily = payload["daily"]
    days = [
        DailyWeather(
            date=d,
            snowfall_cm=daily["snowfall_sum"][i],
            precipitation_mm=daily["precipitation_sum"][i],
            tmax_c=daily["temperature_2m_max"][i],
            tmin_c=daily["temperature_2m_min"][i],
            gust_max_kmh=daily["wind_gusts_10m_max"][i],
        )
        for i, d in enumerate(daily["time"])
    ]
    return WeatherDataset(
        hub_id=hub_id,
        start_date=days[0].date,
        end_date=days[-1].date,
        retrieved_at=retrieved_at,
        days=days,
    )


def fetch_weather(hub: Hub, client: httpx.Client | None = None) -> WeatherDataset:
    params = {
        "latitude": hub.lat,
        "longitude": hub.lon,
        "start_date": WINDOW_START.isoformat(),
        "end_date": WINDOW_END.isoformat(),
        "daily": DAILY_VARS,
        "timezone": hub.timezone,
        "models": "era5",
    }
    with client or _client() as c:
        return parse_open_meteo(hub.id, _get_json(c, OPEN_METEO_URL, params), _now())


# ---------- FEMA National Risk Index ----------

def parse_nri_features(features: list[dict]) -> tuple[list[NriCounty], str]:
    counties = []
    version = ""
    for feature in features:
        a = feature["attributes"]
        version = a.get("NRI_VER") or version
        counties.append(
            NriCounty(
                fips=a["STCOFIPS"],
                county=a["COUNTY"],
                state=a["STATEABBRV"],
                afreq={code: a.get(f"{code}_AFREQ") for code in NRI_HAZARD_CODES},
            )
        )
    return counties, version


def fetch_nri(client: httpx.Client | None = None) -> NriDataset:
    out_fields = ",".join(
        ["STCOFIPS", "COUNTY", "STATEABBRV", "NRI_VER"] + [f"{c}_AFREQ" for c in NRI_HAZARD_CODES]
    )
    counties: list[NriCounty] = []
    version = ""
    offset = 0
    with client or _client() as c:
        while True:
            page = _get_json(c, NRI_URL, {
                "where": "1=1",
                "outFields": out_fields,
                "returnGeometry": "false",
                "orderByFields": "STCOFIPS",
                "resultOffset": offset,
                "resultRecordCount": NRI_PAGE_SIZE,
                "f": "json",
            })
            if "error" in page:
                raise SourceError(f"FEMA NRI query failed: {page['error'].get('message', 'unknown')}")
            batch, page_version = parse_nri_features(page.get("features", []))
            counties += batch
            version = page_version or version
            if not batch or not page.get("exceededTransferLimit"):
                break
            offset += len(batch)
    if len(counties) < 3000:
        raise SourceError(f"FEMA NRI returned only {len(counties)} counties; expected about 3,232")
    return NriDataset(version=version, retrieved_at=_now(), counties=counties)
