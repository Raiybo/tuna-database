"""Open-Meteo Marine API: SST, waves, and ocean currents (free, no key).

https://open-meteo.com/en/docs/marine-weather-api
"""
from __future__ import annotations

from ._http import get_json, hour_index

API = "https://marine-api.open-meteo.com/v1/marine"


def fetch(lat: float, lon: float) -> dict:
    url = (
        f"{API}?latitude={lat}&longitude={lon}"
        "&current=sea_surface_temperature,wave_height,ocean_current_velocity,ocean_current_direction"
        "&hourly=sea_surface_temperature,wave_height,wave_period"
        "&timezone=auto&forecast_days=1"
    )
    d = get_json(url)
    cur = d.get("current", {})
    h = d.get("hourly", {})
    times = h.get("time", [])
    idx = hour_index(times, cur.get("time"))
    wp = h.get("wave_period", [])
    ssts = [v for v in h.get("sea_surface_temperature", []) if v is not None]
    waves = [v for v in h.get("wave_height", []) if v is not None]
    return {
        "sst": cur.get("sea_surface_temperature"),
        "wave": cur.get("wave_height"),
        "wave_period": wp[idx] if 0 <= idx < len(wp) else None,
        "current_kmh": cur.get("ocean_current_velocity"),
        "current_dir": cur.get("ocean_current_direction"),
        "sst_min": min(ssts) if ssts else None,
        "sst_max": max(ssts) if ssts else None,
        "wave_max": max(waves) if waves else None,
        "hour_label": cur.get("time"),
        "utc_offset_sec": int(d.get("utc_offset_seconds", 0)),
    }
