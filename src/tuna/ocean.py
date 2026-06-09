"""Daily 'ocean today + go/no-go' summary - the live sheet."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from . import config
from .conditions import compass


def _vals(reports, getter):
    out = []
    for r in reports:
        v = getter(r)
        if v is not None:
            out.append(v)
    return out


@dataclass
class Ocean:
    date_label: str
    home_name: str
    verdict: str
    verdict_reason: str
    reference_area: str
    sst_avg: float | None
    sst_min: float | None
    sst_max: float | None
    wave_min: float | None
    wave_max: float | None
    wind_min: float | None
    wind_max: float | None
    wind_dir: float | None
    gust_max: float | None
    pressure: float | None
    pressure_trend: float | None
    current_avg: float | None
    cloud: float | None
    front_spread: float | None
    moon: dict
    best_in_range: object | None
    n_in_range: int
    chl_enabled: bool
    has_sightings: bool


def build(reports, solunar: dict, home, now_label: str, sightings) -> Ocean:
    in_range = [r for r in reports if r.cond.in_range]
    pool = in_range or reports
    ref = min(pool, key=lambda r: r.cond.dist_km) if pool else None

    ssts = _vals(pool, lambda r: r.cond.marine.get("sst"))
    waves = _vals(pool, lambda r: r.cond.marine.get("wave"))
    winds = _vals(pool, lambda r: r.cond.weather.get("wind_kmh"))
    gusts = _vals(pool, lambda r: r.cond.weather.get("gust_kmh"))
    currents = _vals(pool, lambda r: r.cond.marine.get("current_kmh"))
    spread = (max(ssts) - min(ssts)) if len(ssts) >= 2 else None

    best = max(in_range, key=lambda r: r.score.total) if in_range else (
        max(reports, key=lambda r: r.score.total) if reports else None)

    # Verdict: blow-out guard first, then best in-range score.
    verdict, reason = "SLOW", "conditions modest today"
    max_wind = max(winds) if winds else 0
    max_wave = max(waves) if waves else 0
    sky = ref.cond.weather.get("cloud") if ref else None
    if max_wind > config.BLOWOUT_WIND_KMH or max_wave > config.BLOWOUT_WAVE_M:
        verdict = "TOUGH"
        reason = f"blown out - wind to {max_wind:.0f} km/h, swell to {max_wave:.1f} m"
    elif best:
        s = best.score.total
        wd = compass(ref.cond.weather.get("wind_dir")) if ref else "?"
        cond_bits = []
        if winds:
            cond_bits.append(f"{min(winds):.0f}-{max(winds):.0f} km/h {wd} wind")
        if waves:
            cond_bits.append(f"{min(waves):.1f}-{max(waves):.1f} m swell")
        if ssts:
            cond_bits.append(f"water {mean(ssts):.1f} C")
        tail = ", ".join(cond_bits)
        if s >= 0.70:
            verdict, reason = "GO", tail
        elif s >= 0.55:
            verdict, reason = "DECENT", tail
        elif s >= 0.40:
            verdict, reason = "MARGINAL", tail
        else:
            verdict, reason = "SLOW", tail

    return Ocean(
        date_label=now_label,
        home_name=home.name,
        verdict=verdict,
        verdict_reason=reason,
        reference_area=ref.spot.area if ref else "",
        sst_avg=round(mean(ssts), 1) if ssts else None,
        sst_min=min(ssts) if ssts else None,
        sst_max=max(ssts) if ssts else None,
        wave_min=min(waves) if waves else None,
        wave_max=max(waves) if waves else None,
        wind_min=min(winds) if winds else None,
        wind_max=max(winds) if winds else None,
        wind_dir=ref.cond.weather.get("wind_dir") if ref else None,
        gust_max=max(gusts) if gusts else None,
        pressure=ref.cond.weather.get("pressure") if ref else None,
        pressure_trend=ref.cond.weather.get("pressure_trend") if ref else None,
        current_avg=round(mean(currents), 1) if currents else None,
        cloud=sky,
        front_spread=round(spread, 1) if spread is not None else None,
        moon=solunar,
        best_in_range=best,
        n_in_range=len(in_range),
        chl_enabled=config.CHL_ENABLED,
        has_sightings=bool(sightings),
    )
