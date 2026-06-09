"""Moon phase + approximate solunar feeding periods (computed locally, no network).

Major periods occur near lunar transit (moon overhead) and anti-transit
(underfoot); minor periods near moonrise/moonset. We approximate the lunar
transit time from the moon's elongation relative to the sun - good enough for
planning, and labelled as approximate. The day score peaks at new and full moon.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

SYNODIC = 29.53058867
_REF_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)

_PHASE_NAMES = (
    "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
    "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
)


def _moon_fraction(now_utc: datetime) -> float:
    age = ((now_utc - _REF_NEW_MOON).total_seconds() / 86400.0) % SYNODIC
    return age / SYNODIC


def _hhmm(minutes: float) -> str:
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def solunar(now_utc: datetime, lon: float, utc_offset_sec: int) -> dict:
    f = _moon_fraction(now_utc)
    name = _PHASE_NAMES[int(f * 8 + 0.5) % 8]
    illum = round((1 - math.cos(2 * math.pi * f)) / 2 * 100)

    # Local solar noon (minutes after local midnight) from longitude & tz.
    offset_h = utc_offset_sec / 3600.0
    solar_noon = 720 - 4 * (lon - 15 * offset_h)
    # Lunar transit lags the sun by the elongation: ~24h * fraction-of-month.
    transit = (solar_noon + 1440 * f) % 1440

    majors = [_hhmm(transit), _hhmm(transit + 720)]
    minors = [_hhmm(transit - 360), _hhmm(transit + 360)]
    # Strongest at new/full (|cos| = 1), weakest at quarters.
    day_score = round(0.55 + 0.45 * abs(math.cos(2 * math.pi * f)), 3)

    return {
        "phase": name,
        "illumination_pct": illum,
        "day_score": day_score,
        "major_periods": majors,
        "minor_periods": minors,
    }
