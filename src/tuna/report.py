"""Assemble the daily bluefin casting report from spots + live marine data."""
from __future__ import annotations

from dataclasses import dataclass

from . import config, scoring
from .marine import Marine, fetch_marine
from .spots import Spot, load_spots


@dataclass
class SpotReport:
    spot: Spot
    marine: Marine
    suit: scoring.Suitability
    rating: str


def build_report(spots: list[Spot] | None = None) -> list[SpotReport]:
    """Fetch conditions for every spot, score them, and return ranked best-first."""
    spots = spots if spots is not None else load_spots()
    marines = [fetch_marine(s.lat, s.lon) for s in spots]
    fronts = scoring.front_scores([m.sst_now for m in marines])

    reports: list[SpotReport] = []
    for spot, m, front in zip(spots, marines, fronts):
        sst_s = scoring.sst_score(m.sst_now) if m.sst_now is not None else 0.0
        wave_s = scoring.wave_score(m.wave_now) if m.wave_now is not None else 0.0
        suit = scoring.combine(sst_s, wave_s, front)
        reports.append(SpotReport(spot, m, suit, config.rating(suit.total)))

    reports.sort(key=lambda r: r.suit.total, reverse=True)
    return reports
