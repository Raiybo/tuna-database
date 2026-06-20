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
    "sst": 0.22,
    "front": 0.13,
    "bait": 0.15,         # chlorophyll; omitted when disabled/stale
    "current": 0.10,
    "castability": 0.17,
    "pressure": 0.10,
    "solunar": 0.13,
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
    "sst": 0.16,
    "front": 0.11,
    "bait": 0.12,
    "current": 0.08,
    "castability": 0.16,
    "pressure": 0.09,
    "solunar": 0.10,
    "feeding": 0.18,
}

# A contiguous bite window = the run of hours whose score is within this of the peak.
WINDOW_DROP = 0.06

# Pattern detection: pre-frontal pressure-fall band (hPa / 3h).
PRESSURE_FEED_LOW = -3.0
PRESSURE_FEED_HIGH = -0.5

# How recent a logged catch stays useful for pattern-learning (days).
CATCH_MEMORY_DAYS = 400


def rating(score: float) -> str:
    """Map a 0..1 suitability score to a label."""
    if score >= 0.75:
        return "PRIME"
    if score >= 0.55:
        return "GOOD"
    if score >= 0.35:
        return "FAIR"
    return "POOR"
