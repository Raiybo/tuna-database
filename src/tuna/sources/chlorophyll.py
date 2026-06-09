"""Chlorophyll-a (bait / productivity proxy) via NOAA ERDDAP griddap.

This is the designated extension point for the "bait in the water" signal.
It tries a chain of (server, dataset, variable) candidates and returns the
first value it can parse, together with the observation date and its age in
days. The caller (conditions.py) only *uses* the value when it is fresh
(<= config.CHL_MAX_AGE_DAYS) and config.CHL_ENABLED is true.

The free MODIS/VIIRS feeds reachable without a login are currently frozen
(~2022), so chlorophyll is disabled by default. To fortify: add a fresh source
(e.g. a Copernicus Marine subset, or your own gridded product) to CANDIDATES
and set config.CHL_ENABLED = True - the model weight renormalises automatically.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ._http import get_text

# (base_url, dataset_id, variable_name)
CANDIDATES = (
    ("https://coastwatch.pfeg.noaa.gov/erddap", "erdMH1chla8day", "chlorophyll"),
    ("https://coastwatch.pfeg.noaa.gov/erddap", "erdVH2018chla8day", "chla"),
)


def fetch(lat: float, lon: float, timeout: int = 12) -> dict:
    for base, ds, var in CANDIDATES:
        try:
            url = (
                f"{base}/griddap/{ds}.csv?"
                f"{var}%5B(last)%5D%5B({lat}):({lat})%5D%5B({lon}):({lon})%5D"
            )
            txt = get_text(url, retries=1, timeout=timeout)
            row = txt.strip().splitlines()[-1].split(",")
            val = float(row[-1])
            if math.isnan(val):
                continue
            dt = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - dt).days
            return {"value": val, "date": row[0][:10], "age_days": age, "source": ds}
        except Exception:
            continue
    return {"value": None, "date": None, "age_days": None, "source": None}
