"""Chlorophyll-a (bait / productivity proxy) via NOAA ERDDAP griddap.

This is the "bait in the water" signal. The classic free MODIS/VIIRS feeds on
coastwatch.pfeg.noaa.gov are frozen (~2022) and that server is often
unreachable; the live, near-real-time source that actually works is NOAA
OceanWatch (PIFSC): the S-NPP VIIRS chlorophyll product.

Ocean colour is cloud-gapped, so a single exact pixel is frequently empty. We
therefore pull a small box around the point and return the NEAREST valid pixel,
preferring the freshest dataset (daily) and falling back to the better-covered
weekly composite. The caller (conditions.py) only uses the value when it is
fresh (<= config.CHL_MAX_AGE_DAYS) and config.CHL_ENABLED is true.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from ._http import get_text

# (base_url, dataset_id, variable_name, has_altitude_dim)
CANDIDATES = (
    ("https://oceanwatch.pifsc.noaa.gov/erddap", "noaa_snpp_chla_daily", "chlor_a", True),
    ("https://oceanwatch.pifsc.noaa.gov/erddap", "noaa_snpp_chla_weekly", "chlor_a", True),
)

BOX_DEG = 0.08   # +/- around the point (~9 km) to dodge cloud gaps


def _approx_km(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 111.0
    dlon = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def fetch(lat: float, lon: float, timeout: int = 15) -> dict:
    for base, ds, var, has_alt in CANDIDATES:
        try:
            alt = "%5B0%5D" if has_alt else ""
            box = (f"%5B({lat - BOX_DEG}):({lat + BOX_DEG})%5D"
                   f"%5B({lon - BOX_DEG}):({lon + BOX_DEG})%5D")
            url = f"{base}/griddap/{ds}.csv?{var}%5B(last)%5D{alt}{box}"
            txt = get_text(url, retries=2, timeout=timeout)
            lines = txt.strip().splitlines()
            if len(lines) < 3:
                continue
            cols = lines[0].split(",")
            li, oi, vi = cols.index("latitude"), cols.index("longitude"), len(cols) - 1
            best = None
            best_d = 1e9
            date_str = None
            for row in lines[2:]:                       # skip header + units rows
                f = row.split(",")
                raw = f[vi].strip()
                if raw in ("", "NaN"):
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                if math.isnan(val):
                    continue
                d = _approx_km(lat, lon, float(f[li]), float(f[oi]))
                if d < best_d:
                    best_d, best, date_str = d, val, f[0]
            if best is None:
                continue
            dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - dt).days
            return {"value": best, "date": date_str[:10], "age_days": age,
                    "source": ds, "pixel_km": round(best_d, 1)}
        except Exception:
            continue
    return {"value": None, "date": None, "age_days": None, "source": None}
