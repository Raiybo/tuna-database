"""Orchestrate the daily report: gather live data, score, rank, summarise."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import conditions as conditions_mod
from . import model, ocean, scoring, seasonality
from .conditions import Conditions
from .sources import solunar as solunar_mod
from .spots import Home, Spot, load_home, load_sightings, load_spots


@dataclass
class SpotReport:
    spot: Spot
    cond: Conditions
    score: model.SpotScore


@dataclass
class Report:
    ocean: ocean.Ocean
    spots: list          # ranked SpotReport, best first
    home: Home


def build_report(enable_chl: bool | None = None,
                 home_override: Home | None = None) -> Report:
    spots = load_spots()
    home = home_override or load_home()
    sightings = load_sightings()

    conds = conditions_mod.gather(spots, home, enable_chl)
    fronts = scoring.front_scores([c.marine.get("sst") for c in conds])

    offset = next((c.marine.get("utc_offset_sec") for c in conds
                   if c.marine.get("utc_offset_sec") is not None), 7200)
    now = datetime.now(timezone.utc)
    sol = solunar_mod.solunar(now, home.lon, offset)
    local = now + timedelta(seconds=offset)
    seasonal = seasonality.month_score(local.month)

    reports = []
    for spot, cond, front in zip(spots, conds, fronts):
        sc = model.score(spot, cond, front, sol["day_score"], sightings, now,
                         seasonal_score=seasonal)
        reports.append(SpotReport(spot, cond, sc))
    reports.sort(key=lambda r: r.score.total, reverse=True)

    label = next((c.marine.get("hour_label") for c in conds
                  if c.marine.get("hour_label")), now.strftime("%Y-%m-%dT%H:%M"))
    summary = ocean.build(reports, sol, home, label, sightings)
    return Report(ocean=summary, spots=reports, home=home)
