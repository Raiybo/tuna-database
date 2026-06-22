"""Seasonal bluefin-presence prior for the Eastern Mediterranean (Lebanon).

Atlantic bluefin tuna run through the warm Levantine basin mainly from late
spring into autumn, peaking in high summer; winter inshore odds are lower. This
is a *presence* prior - it shifts the day-level verdict, not where the fish sit
on a given day (that's the spatial finder/front work).

These monthly weights are a heuristic from general Mediterranean bluefin
seasonality and ICCAT migration timing - edit them as your own logbook tells you.
"""
from __future__ import annotations

# month (1-12) -> 0..1 likelihood that bluefin are around and catchable inshore
MONTHLY = {
    1: 0.25, 2: 0.25, 3: 0.35, 4: 0.55, 5: 0.80, 6: 0.95,
    7: 1.00, 8: 1.00, 9: 0.95, 10: 0.80, 11: 0.55, 12: 0.35,
}


def month_score(when) -> float:
    """Accepts a month int (1-12) or a 'YYYY-MM-DD' / 'YYYY-MM...' date string."""
    if isinstance(when, str):
        month = int(when[5:7])
    else:
        month = int(when)
    return MONTHLY.get(month, 0.5)


def label(score: float) -> str:
    if score >= 0.9:
        return "peak season"
    if score >= 0.7:
        return "strong season"
    if score >= 0.45:
        return "shoulder season"
    return "off season"
