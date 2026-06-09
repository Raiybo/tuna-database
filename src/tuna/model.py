"""Turn a spot's Conditions into a 0..1 bluefin suitability score."""
from __future__ import annotations

from dataclasses import dataclass

from . import config, scoring
from .conditions import Conditions
from .spots import Spot


@dataclass
class SpotScore:
    base: float           # weighted blend of live factors
    boost: float          # additive boost from recent sightings
    total: float          # min(1, base + boost)
    rating: str
    contrib: dict         # factor -> 0..1 score actually used


def score(spot: Spot, cond: Conditions, front_score: float,
          solunar_score: float, sightings, now) -> SpotScore:
    m, w = cond.marine, cond.weather

    factors = {
        "sst": scoring.sst_score(m["sst"]) if m.get("sst") is not None else None,
        "front": front_score,
        "bait": scoring.bait_score(cond.chl_used),
        "current": (scoring.current_score(m["current_kmh"])
                    if m.get("current_kmh") is not None else None),
        "castability": scoring.castability_score(m.get("wave"), w.get("wind_kmh")),
        "pressure": scoring.pressure_score(w.get("pressure_trend")),
        "solunar": solunar_score,
    }
    base, contrib = scoring.combine_weighted(factors)
    boost = scoring.sighting_boost(spot.lat, spot.lon, sightings, now)
    total = round(min(1.0, base + boost), 4)
    return SpotScore(base=base, boost=boost, total=total,
                     rating=config.rating(total), contrib=contrib)
