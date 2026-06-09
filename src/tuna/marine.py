"""Open-Meteo Marine API client (standard library only).

Docs: https://open-meteo.com/en/docs/marine-weather-api
Free, no API key, CORS-enabled. We pull hourly sea-surface temperature and
significant wave height for a point, then pick the value for the current local
hour using the timezone offset the API returns.
"""
from __future__ import annotations

import json
import ssl
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

API = "https://marine-api.open-meteo.com/v1/marine"


def _ssl_context() -> ssl.SSLContext:
    """Verified TLS context. Prefer certifi's CA bundle if installed so this
    works on Python builds that aren't linked to the system trust store
    (e.g. python.org installs on macOS); otherwise use the system default."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


_SSL = _ssl_context()


@dataclass
class Marine:
    sst_now: float | None
    wave_now: float | None
    sst_min: float | None
    sst_max: float | None
    wave_max: float | None
    hour_label: str


def _get(url: str, retries: int = 3, timeout: int = 20) -> dict:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "tuna-database/0.1"})
            with urlopen(req, timeout=timeout, context=_SSL) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"Marine API request failed after {retries} tries: {last}")


def fetch_marine(lat: float, lon: float) -> Marine:
    """Fetch today's marine conditions for a single point."""
    url = (
        f"{API}?latitude={lat}&longitude={lon}"
        "&hourly=sea_surface_temperature,wave_height"
        "&timezone=auto&forecast_days=1"
    )
    data = _get(url)
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    ssts = hourly.get("sea_surface_temperature", [])
    waves = hourly.get("wave_height", [])

    offset = int(data.get("utc_offset_seconds", 0))
    now_local = datetime.now(timezone.utc) + timedelta(seconds=offset)
    label = now_local.strftime("%Y-%m-%dT%H:00")
    idx = times.index(label) if label in times else _nearest_idx(times, now_local)

    sst_clean = [v for v in ssts if v is not None]
    wave_clean = [v for v in waves if v is not None]
    return Marine(
        sst_now=_at(ssts, idx),
        wave_now=_at(waves, idx),
        sst_min=min(sst_clean) if sst_clean else None,
        sst_max=max(sst_clean) if sst_clean else None,
        wave_max=max(wave_clean) if wave_clean else None,
        hour_label=times[idx] if 0 <= idx < len(times) else label,
    )


def _at(seq, idx):
    return seq[idx] if 0 <= idx < len(seq) else None


def _nearest_idx(times, now_local) -> int:
    """Fallback when the exact hour label isn't present: match hour-of-day."""
    target = now_local.strftime("T%H:00")
    for i, t in enumerate(times):
        if t.endswith(target):
            return i
    return min(12, len(times) - 1) if times else 0
