"""Open-Meteo Weather API: wind, gusts, barometric trend, cloud (free, no key).

https://open-meteo.com/en/docs
Pressure trend over the last 3h is a useful bite indicator, so we pull the
hourly pressure series (incl. the past day) and difference it.
"""
from __future__ import annotations

from ._http import get_json, hour_index

API = "https://api.open-meteo.com/v1/forecast"


def fetch(lat: float, lon: float) -> dict:
    url = (
        f"{API}?latitude={lat}&longitude={lon}"
        "&current=wind_speed_10m,wind_gusts_10m,wind_direction_10m,surface_pressure,cloud_cover"
        "&hourly=surface_pressure"
        "&timezone=auto&past_days=1&forecast_days=1"
    )
    d = get_json(url)
    cur = d.get("current", {})
    h = d.get("hourly", {})
    times = h.get("time", [])
    pres = h.get("surface_pressure", [])
    idx = hour_index(times, cur.get("time"))

    trend = None
    if 0 <= idx < len(pres) and idx - 3 >= 0:
        now_p, prev_p = pres[idx], pres[idx - 3]
        if now_p is not None and prev_p is not None:
            trend = round(now_p - prev_p, 2)

    return {
        "wind_kmh": cur.get("wind_speed_10m"),
        "gust_kmh": cur.get("wind_gusts_10m"),
        "wind_dir": cur.get("wind_direction_10m"),
        "pressure": cur.get("surface_pressure"),
        "pressure_trend": trend,
        "cloud": cur.get("cloud_cover"),
    }


def fetch_series_multi(spots, days: int) -> list[dict]:
    """Hourly wind/gust/dir/pressure/cloud for every spot over ``days`` days, in
    ONE batched multi-location request. Returns a list aligned with ``spots``."""
    lat = ",".join(f"{s.lat}" for s in spots)
    lon = ",".join(f"{s.lon}" for s in spots)
    url = (
        f"{API}?latitude={lat}&longitude={lon}"
        "&hourly=wind_speed_10m,wind_gusts_10m,wind_direction_10m,surface_pressure,cloud_cover"
        f"&timezone=auto&forecast_days={days}"
    )
    d = get_json(url)
    if isinstance(d, dict):
        d = [d]
    out = []
    for x in d:
        h = x.get("hourly", {})
        out.append({
            "time": h.get("time", []),
            "wind": h.get("wind_speed_10m", []),
            "gust": h.get("wind_gusts_10m", []),
            "wind_dir": h.get("wind_direction_10m", []),
            "pressure": h.get("surface_pressure", []),
            "cloud": h.get("cloud_cover", []),
        })
    return out
