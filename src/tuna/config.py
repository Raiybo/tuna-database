"""Tuning constants for bluefin casting-suitability scoring.

Everything here is meant to be edited. These numbers encode assumptions about
when and where Atlantic bluefin tuna (Thunnus thynnus) are catchable by casting
along the Lebanese (Eastern Mediterranean) coast. Sea temperatures are in
degrees Celsius; wave heights are significant wave height in metres.
"""
from __future__ import annotations

# Sea-surface-temperature suitability bands: (low, high, score).
# Evaluated tightest-first; the first band that contains the temperature wins.
# Anything outside every band scores SST_FLOOR. The optimal window reflects the
# warm Eastern-Med summer feeding period when bluefin work bait near the surface.
SST_BANDS = (
    (18.0, 24.0, 1.0),   # optimal feeding / surface-casting window
    (16.0, 26.0, 0.6),   # workable shoulder
    (14.0, 28.0, 0.3),   # marginal
)
SST_FLOOR = 0.1

# Castability by significant wave height: (max_height, score), smallest first.
WAVE_BANDS = (
    (0.8, 1.0),   # glassy -> ideal for poppers / stickbaits
    (1.5, 0.7),   # fishable chop
    (2.0, 0.4),   # rough but castable from a boat
)
WAVE_FLOOR = 0.1     # > 2 m: unsafe / very hard to cast

# How much each factor contributes to the final 0..1 suitability score.
WEIGHT_SST = 0.55
WEIGHT_WAVE = 0.30
WEIGHT_FRONT = 0.15

# Thermal-break ("front") heuristic. Below this regional spread (deg C) we treat
# the water as uniform and give every spot the baseline front score.
FRONT_MIN_SPREAD = 0.5
FRONT_BASELINE = 0.3

# Prime surface-casting windows (local hour ranges) - guidance only.
PRIME_WINDOWS = ((5, 8), (18, 20))


def rating(score: float) -> str:
    """Map a 0..1 suitability score to a human label."""
    if score >= 0.75:
        return "PRIME"
    if score >= 0.55:
        return "GOOD"
    if score >= 0.35:
        return "FAIR"
    return "POOR"
