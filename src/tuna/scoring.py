"""Pure scoring functions - no I/O, fully unit-testable."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from . import config


def sst_score(sst: float) -> float:
    """Score sea-surface temperature against the configured bands."""
    for low, high, score in config.SST_BANDS:
        if low <= sst <= high:
            return score
    return config.SST_FLOOR


def wave_score(wave_height: float) -> float:
    """Score castability from significant wave height (lower = better)."""
    for max_h, score in config.WAVE_BANDS:
        if wave_height <= max_h:
            return score
    return config.WAVE_FLOOR


def front_scores(ssts):
    """Heuristic 'thermal edge' score per spot, aligned with the input order.

    Bluefin and their bait stack along temperature breaks. Spots whose SST sits
    far from the regional median - i.e. on the warm or cold edge of a break -
    score higher. A flat-temperature day scores every spot at baseline.
    ``None`` entries (missing data) get the baseline.
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


@dataclass
class Suitability:
    total: float
    sst: float
    wave: float
    front: float


def combine(sst_s: float, wave_s: float, front_s: float) -> Suitability:
    """Weighted blend of the three factor scores into a final 0..1 score."""
    total = (
        config.WEIGHT_SST * sst_s
        + config.WEIGHT_WAVE * wave_s
        + config.WEIGHT_FRONT * front_s
    )
    return Suitability(round(total, 4), sst_s, wave_s, front_s)
