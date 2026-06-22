"""Tuning constants for the bluefin go/no-go model.

Everything here is meant to be edited - these numbers encode assumptions about
when and where Atlantic bluefin tuna (Thunnus thynnus) are catchable by casting
along the Lebanese (Eastern Mediterranean) coast. Units: temperature deg C,
wave height m, wind & ocean current km/h, pressure hPa, chlorophyll mg/m^3.

The model blends several independent live sources. Each factor can be missing
(source down / disabled); WEIGHTS are renormalised over whatever is available,
so the score stays meaningful and the system degrades gracefully.
"""
from __future__ import annotations

# --- sea-surface temperature: (low, high, score), tightest band first ---
SST_BANDS = (
    (18.0, 24.0, 1.0),   # optimal warm-season feeding window
    (16.0, 26.0, 0.6),
    (14.0, 28.0, 0.3),
)
SST_FLOOR = 0.1

# --- castability sub-factors ---
WAVE_BANDS = ((0.8, 1.0), (1.5, 0.7), (2.0, 0.4))   # (max_height, score)
WAVE_FLOOR = 0.1
WIND_BANDS = ((8, 1.0), (15, 0.9), (22, 0.7), (30, 0.45), (40, 0.2))  # (max_kmh, score)
WIND_FLOOR = 0.05
CAST_WAVE_W = 0.55
CAST_WIND_W = 0.45

# --- ocean current (km/h): a moderate drift makes feeding edges ---
CURRENT_BANDS = ((0.3, 0.45), (2.5, 1.0), (5.0, 0.7), (9.0, 0.45))
CURRENT_FLOOR = 0.3

# --- barometric trend over 3h (hPa): (low, high, score) ---
PRESSURE_BANDS = (
    (float("-inf"), -3.0, 0.40),   # dropping fast -> storm / rough
    (-3.0, -1.5, 0.70),            # falling -> often a feed before a front
    (-1.5, -0.5, 1.00),            # slowly falling -> prime
    (-0.5, 0.5, 0.90),             # steady
    (0.5, 1.5, 0.70),              # rising
    (1.5, float("inf"), 0.45),     # rising fast -> bluebird, slower bite
)
PRESSURE_FLOOR = 0.5

# --- chlorophyll-a as a bait/productivity proxy (mg/m^3) ---
CHL_BANDS = (
    (0.0, 0.05, 0.30),   # blue desert, low forage
    (0.05, 0.15, 0.60),
    (0.15, 0.60, 1.00),  # productive frontal / coastal water
    (0.60, 1.50, 0.70),
)
CHL_FLOOR = 0.40          # >= 1.5: murky / post-bloom
CHL_ENABLED = True        # live: NOAA OceanWatch S-NPP VIIRS chlorophyll (see sources/chlorophyll.py)
CHL_MAX_AGE_DAYS = 21     # VIIRS NRT chl lags ~1-2 weeks; ignore anything older

# --- thermal-break ("front") heuristic across the spot field ---
FRONT_MIN_SPREAD = 0.5
FRONT_BASELINE = 0.3

# --- how much each live factor contributes (renormalised over available ones) ---
WEIGHTS = {
    "sst": 0.20,
    "front": 0.12,
    "bait": 0.14,         # chlorophyll; omitted when disabled/stale
    "current": 0.09,
    "castability": 0.16,
    "pressure": 0.09,
    "solunar": 0.10,
    "seasonal": 0.10,     # month-of-year bluefin presence prior (Eastern Med)
}

# --- recent real sightings boost a spot on top of the modelled score ---
SIGHTING_MAX = 0.15
SIGHTING_RADIUS_KM = 15.0
SIGHTING_DAYS = 3.0

# --- prime surface-casting light windows (local hour ranges) ---
PRIME_WINDOWS = ((5, 8), (18, 20))

# --- blow-out guards for the daily ocean verdict ---
BLOWOUT_WIND_KMH = 35.0
BLOWOUT_WAVE_M = 2.0

# --- forecast (multi-day, hourly) ---------------------------------------------
FORECAST_DAYS = 5
DAYLIGHT_HOURS = range(4, 22)     # local hours evaluated for the bite curve

# Time-of-day "feeding" score: prime light windows + solunar major/minor times.
FEEDING_BASELINE = 0.30
FEEDING_LIGHT_EDGE_H = 1.0        # taper this many hours outside a prime window
FEEDING_SOLUNAR_MAJOR_H = 0.75   # within this of a major -> full strength
FEEDING_SOLUNAR_MINOR_H = 0.75
FEEDING_SOLUNAR_MINOR_STRENGTH = 0.70

# Hourly model weights (adds a time-of-day 'feeding' factor; renormalised like WEIGHTS).
WEIGHTS_HOURLY = {
    "sst": 0.15,
    "front": 0.10,
    "bait": 0.11,
    "current": 0.07,
    "castability": 0.15,
    "pressure": 0.08,
    "solunar": 0.09,
    "feeding": 0.15,
    "seasonal": 0.10,
}

# A contiguous bite window = the run of hours whose score is within this of the peak.
WINDOW_DROP = 0.06

# Pattern detection: pre-frontal pressure-fall band (hPa / 3h).
PRESSURE_FEED_LOW = -3.0
PRESSURE_FEED_HIGH = -0.5

# How recent a logged catch stays useful for pattern-learning (days).
CATCH_MEMORY_DAYS = 400

# --- gridded fish-finder (finder.py) ------------------------------------------
FINDER_SEARCH_KM = 24.0         # scan radius from the marina
FINDER_GRAD_KM = 4.0            # neighbourhood for front / gradient calcs
FINDER_MAX_CELLS = 150          # cap scored cells (keeps API calls sane / free)
FINDER_N_HOTSPOTS = 8
FINDER_MIN_SEP_KM = 3.5         # de-cluster spacing between hotspots
FINDER_MIN_DEPTH_M = 30.0       # require real offshore water (never land/shoal)

# Normalisers: signal value that maps to a full 1.0 score.
SST_FRONT_NORM = 0.12           # deg C across the gradient neighbourhood
CHL_FRONT_NORM = 0.10           # mg/m^3 across the neighbourhood
CHL_ANOM_NORM = 0.6             # fractional chlorophyll anomaly vs local median
CONVERGENCE_NORM = 0.8          # current convergence (km/h per neighbourhood)
STRUCTURE_NORM = 120.0          # depth change (m) across the neighbourhood = shelf break

# Per-cell fish-likelihood weights (spatial signals only; renormalised).
FINDER_WEIGHTS = {
    "sst_front": 0.32,
    "convergence": 0.22,
    "chl_anom": 0.16,
    "chl_front": 0.16,
    "structure": 0.14,
}
FINDER_STRONG = 0.60            # a signal at/above this "agrees"; >=3 agree = High confidence


def rating(score: float) -> str:
    """Map a 0..1 suitability score to a label."""
    if score >= 0.75:
        return "PRIME"
    if score >= 0.55:
        return "GOOD"
    if score >= 0.35:
        return "FAIR"
    return "POOR"
