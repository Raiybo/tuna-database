#!/usr/bin/env python3
"""Generate data/hotspots.json - the gridded bait-likelihood hotspots.

Thin runner around src/tuna/finder.py (the engine). Scores the water within
range of the marina on SST fronts x chlorophyll x current edges x structure,
with multi-signal-agreement confidence. The web map plots the result.

Also attaches the Global Fishing Watch fleet-activity layer when GFW_TOKEN is
set. That stays OUT of the score on purpose: where the commercial fleet works
is observed evidence, not a modelled signal, so it rides along as its own map
layer instead of quietly inflating a cell's confidence.

    PYTHONPATH=src python tools/hotspots.py
"""
from __future__ import annotations

import json
import os

from tuna.finder import find
from tuna.sources import ais
from tuna.spots import load_home

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    print("Scanning gridded SST / chlorophyll / currents / bathymetry ...")
    home = load_home()
    out = find(home)
    out["fleet"] = ais.fetch_effort(home.lat, home.lon)
    path = os.path.join(ROOT, "data", "hotspots.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)

    print(f"Saved {len(out['hotspots'])} hotspots -> {path}")
    print(f"  SST: {out['sst_source']} | chl: {out['chl_source']} | "
          f"{out['cells_scored']} cells | {out['season']}")
    print(f"  fleet: {out['fleet']['note']}")
    for i, h in enumerate(out["hotspots"], 1):
        print(f"  {i}. {h['heading']} {h['dist_nm']}nm  ({h['lat']},{h['lon']})  "
              f"score {h['score']} [{h['confidence']}, {h['agree']} signals]  {h['why']}")


if __name__ == "__main__":
    main()
