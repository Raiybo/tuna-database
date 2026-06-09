"""Pure scoring functions - no I/O, fully unit-testable."""
from __future__ import annotations

import math
from statistics import median

from . import config


def sst_score(t: float) -> float:
    for low, high, score in config.SST_BANDS:
        if low <= t <= high:
            return score
    return config.SST_FLOOR


def wave_score(h: float) -> float:
    for max_h, score in config.WAVE_BANDS:
        if h <= max_h:
            return score
    return config.WAVE_FLOOR


def wind_score(kmh: float) -> float:
    for max_k, score in config.WIND_BANDS:
        if kmh <= max_k:
            return score
    return config.WIND_FLOOR


def current_score(kmh: float) -> float:
    for max_k, score in config.CURRENT_BANDS:
        if kmh <= max_k:
            return score
    return config.CURRENT_FLOOR


def pressure_score(trend_3h):
    if trend_3h is None:
        return None
    for low, high, score in config.PRESSURE_BANDS:
        if low <= trend_3h < high:
            return score
    return config.PRESSURE_FLOOR


def bait_score(chl):
    if chl is None:
        return None
    for low, high, score in config.CHL_BANDS:
        if low <= chl < high:
            return score
    return config.CHL_FLOOR


def castability_score(wave, wind):
    """Blend wave height and wind speed into one 0..1 castability score."""
    ws = wave_score(wave) if wave is not None else None
    nd = wind_score(wind) if wind is not None else None
    if ws is None and nd is None:
        return None
    if ws is None:
        return nd
    if nd is None:
        return ws
    return round(config.CAST_WAVE_W * ws + config.CAST_WIND_W * nd, 4)


def front_scores(ssts):
    """Per-spot 'thermal edge' score aligned with the input order.

    Bait and tuna stack on temperature breaks. Spots whose SST sits far from the
    regional median (the warm or cold edge of a break) score higher; a flat day
    scores everyone at baseline. ``None`` entries get the baseline.
    """
    values = [s for s in ssts if s is not None]
    if not values:
        return [config.FRONT_BASELINE for _ in ssts]
    spread = max(values) - min(values)
    if spread < config.FRONT_MIN_SPREAD:
        return [config.FRONT_BASELINE for _ in ssts]
    mid = median(values)
    half = spread / 2.0
    out = []
    for s in ssts:
        if s is None:
            out.append(config.FRONT_BASELINE)
        else:
            out.append(max(0.0, min(1.0, abs(s - mid) / half)))
    return out


def combine_weighted(factors: dict):
    """Weighted average over present (non-None) factors, renormalised.

    Returns (total_score, contributions) where contributions maps each used
    factor to its 0..1 score. Missing factors simply drop out of the blend.
    """
    num = den = 0.0
    contrib = {}
    for name, score in factors.items():
        weight = config.WEIGHTS.get(name, 0.0)
        if score is None or weight <= 0:
            continue
        num += weight * score
        den += weight
        contrib[name] = round(score, 3)
    total = round(num / den, 4) if den > 0 else 0.0
    return total, contrib


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def sighting_boost(lat, lon, sightings, now):
    """Additive boost (0..SIGHTING_MAX) from recent nearby real sightings."""
    best = 0.0
    for s in sightings:
        dist = haversine_km(lat, lon, s["lat"], s["lon"])
        if dist > config.SIGHTING_RADIUS_KM:
            continue
        age_days = (now - s["_dt"]).total_seconds() / 86400.0
        if age_days < 0 or age_days > config.SIGHTING_DAYS:
            continue
        prox = 1.0 - dist / config.SIGHTING_RADIUS_KM
        rec = 1.0 - age_days / config.SIGHTING_DAYS
        best = max(best, config.SIGHTING_MAX * prox * rec)
    return round(best, 4)
