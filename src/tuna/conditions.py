"""Gather all live sources per spot (in parallel) into one Conditions record."""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import config
from .scoring import haversine_km
from .sources import chlorophyll, openmeteo_marine, openmeteo_weather
from .spots import Home, Spot

_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass(deg) -> str:
    if deg is None:
        return "?"
    return _COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def bearing(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


@dataclass
class Conditions:
    spot: Spot
    dist_km: float
    bearing_deg: float
    marine: dict
    weather: dict
    chl: dict
    chl_used: float | None        # gated chlorophyll value actually fed to the model
    in_range: bool = True
    failed: list = field(default_factory=list)

    @property
    def dist_nm(self) -> float:
        return self.dist_km / 1.852

    @property
    def heading(self) -> str:
        return compass(self.bearing_deg)


def _gather_one(spot: Spot, home: Home, enable_chl: bool) -> Conditions:
    failed = []
    try:
        marine = openmeteo_marine.fetch(spot.lat, spot.lon)
    except Exception as e:
        marine, _ = {}, failed.append(f"marine:{e.__class__.__name__}")
    try:
        weather = openmeteo_weather.fetch(spot.lat, spot.lon)
    except Exception as e:
        weather, _ = {}, failed.append(f"weather:{e.__class__.__name__}")

    chl = {"value": None, "date": None, "age_days": None, "source": None}
    if enable_chl:
        try:
            chl = chlorophyll.fetch(spot.lat, spot.lon)
        except Exception as e:
            failed.append(f"chl:{e.__class__.__name__}")

    chl_used = None
    if (enable_chl and chl.get("value") is not None
            and chl.get("age_days") is not None
            and chl["age_days"] <= config.CHL_MAX_AGE_DAYS):
        chl_used = chl["value"]

    dist = round(haversine_km(home.lat, home.lon, spot.lat, spot.lon), 2)
    return Conditions(
        spot=spot,
        dist_km=dist,
        bearing_deg=round(bearing(home.lat, home.lon, spot.lat, spot.lon)),
        marine=marine, weather=weather, chl=chl, chl_used=chl_used,
        in_range=dist <= home.max_range_km, failed=failed,
    )


def gather(spots, home: Home, enable_chl: bool | None = None) -> list[Conditions]:
    """Fetch conditions for every spot concurrently; order matches ``spots``."""
    if enable_chl is None:
        enable_chl = config.CHL_ENABLED
    with ThreadPoolExecutor(max_workers=min(12, len(spots) or 1)) as ex:
        return list(ex.map(lambda s: _gather_one(s, home, enable_chl), spots))
