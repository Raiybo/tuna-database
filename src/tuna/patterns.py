"""Pattern recognition: detect the setups that stack the odds for bluefin.

Two layers:
  1. Rule-based - the recurring favourable conditions (thermal break, pre-frontal
     pressure fall, a solunar major landing on dawn/dusk, productive water, calm
     casting, strong moon).
  2. Learned - if you log trips in data/catches.json, it compares the day to your
     past *successful* conditions and flags a match. Dormant until you have data,
     so it never invents confidence it hasn't earned.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import config
from .scoring import _hm_to_hours


@dataclass
class Pattern:
    name: str
    note: str
    strong: bool


def _solunar_stacks_light(solunar: dict) -> bool:
    edge = config.FEEDING_LIGHT_EDGE_H
    times = [_hm_to_hours(t) for t in solunar.get("major_periods", [])]
    for m in times:
        for a, b in config.PRIME_WINDOWS:
            if a - edge <= m <= b + edge:
                return True
    return False


def _catch_match(ctx: dict, catches: list) -> int:
    """Count logged CATCHES whose conditions resemble today's (each within a
    tolerance on the dims that were recorded). Returns the best single match's
    dimension-hit count (0 if none / no data)."""
    best = 0
    for c in catches:
        if c.get("result") not in (None, "catch") or c.get("n", 1) in (0, "0"):
            continue
        hits = 0
        if ctx.get("sst") is not None and c.get("sst_c") is not None and abs(ctx["sst"] - c["sst_c"]) <= 1.5:
            hits += 1
        if ctx.get("wind_peak") is not None and c.get("wind_kmh") is not None and abs(ctx["wind_peak"] - c["wind_kmh"]) <= 8:
            hits += 1
        if ctx.get("pressure_trend") is not None and c.get("pressure_trend") is not None and abs(ctx["pressure_trend"] - c["pressure_trend"]) <= 1.5:
            hits += 1
        if ctx.get("moon_phase") and c.get("moon") and ctx["moon_phase"] == c["moon"]:
            hits += 1
        if ctx.get("peak_hour") is not None and c.get("hour") is not None and abs(ctx["peak_hour"] - c["hour"]) <= 2:
            hits += 1
        best = max(best, hits)
    return best


def detect(ctx: dict, catches: list | None = None):
    """Return (patterns, confidence_label). ctx carries the day's key numbers."""
    pats: list[Pattern] = []

    fs = ctx.get("front_spread")
    if fs is not None and fs >= config.FRONT_MIN_SPREAD:
        pats.append(Pattern("Thermal break active",
                            f"{fs:.1f} C spread - bait stacks on the seam", fs >= 0.8))

    pt = ctx.get("pressure_trend")
    if pt is not None and config.PRESSURE_FEED_LOW <= pt <= config.PRESSURE_FEED_HIGH:
        pats.append(Pattern("Pre-frontal feed",
                            f"pressure easing {pt:+.1f} hPa/3h", True))

    if _solunar_stacks_light(ctx.get("solunar", {})):
        pats.append(Pattern("Solunar stack at light",
                            "a moon major lands on the dawn/dusk window", True))

    chl = ctx.get("chl")
    if chl is not None and 0.15 <= chl <= 1.5:
        pats.append(Pattern("Productive water",
                            f"chlorophyll {chl:.2f} mg/m3 - forage present", chl <= 0.6))

    wp, hp = ctx.get("wind_peak"), ctx.get("wave_peak")
    if wp is not None and hp is not None and wp <= 15 and hp <= 0.8:
        pats.append(Pattern("Calm casting window",
                            f"{wp:.0f} km/h wind, {hp:.1f} m swell at peak", True))

    moon = ctx.get("solunar", {})
    if moon.get("day_score", 0) >= 0.9:
        pats.append(Pattern("Strong moon",
                            f"{moon.get('phase','')} - peak solunar energy", True))

    if catches:
        m = _catch_match(ctx, catches)
        if m >= 3:
            pats.append(Pattern("Matches your past catches",
                                f"{m} conditions line up with logged hook-ups", True))

    strong = sum(1 for p in pats if p.strong)
    confidence = "High" if strong >= 3 else "Moderate" if strong == 2 else "Low"
    return pats, confidence
