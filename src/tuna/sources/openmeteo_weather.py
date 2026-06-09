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
