#!/usr/bin/env python3
"""
satellite.py - High-resolution OBSERVED ocean state for the Dbaye area.

Pulls from NOAA OceanWatch ERDDAP (free, no key):
  * SST  : CRW_sst_v3_1 (CoralTemp, 5 km, daily, gap-free)         -> temperature breaks
  * Chl-a: noaa_snpp_chla_daily / _weekly (VIIRS, ~4 km)           -> bait / productivity edges

Robustness: every successful pull is cached to sat_cache.json. If the server is
slow or down, the last good pull is reused (and flagged stale) so the daily
report never fails.

These are OBSERVED satellite fields (yesterday-ish). Ocean fronts persist for
days, so they tell you WHERE the structure is; the live weather/current forecast
(Open-Meteo) tells you the day-to-day conditions on top of it.
"""

import json
import math
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "sat_cache.json")
ERDDAP = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap"

# Box around Marina Dbaye - wider than boat range so we see the front structure.
BOX = {"lat0": 33.70, "lat1": 34.12, "lon0": 35.15, "lon1": 35.62}

MIN_CHLA_PIXELS = 8          # below this the daily chla is too cloud-gapped; fall back
SST_RADIUS_NM = 4.0          # neighbourhood for the SST gradient
CHLA_RADIUS_NM = 4.0


def _approx_nm(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 60.0
    dlon = (lon2 - lon1) * 60.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def _griddap(dataset, var, has_altitude, timeout=70):
    box = f"%5B({BOX['lat0']}):({BOX['lat1']})%5D%5B({BOX['lon0']}):({BOX['lon1']})%5D"
    alt = "%5B0%5D" if has_altitude else ""
    url = f"{ERDDAP}/{dataset}.json?{var}%5B(last)%5D{alt}{box}"
    req = urllib.request.Request(url, headers={"User-Agent": "tuna-forecast/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    cols = data["table"]["columnNames"]
    rows = data["table"]["rows"]
    ti, li, oi = cols.index("time"), cols.index("latitude"), cols.index("longitude")
    vi = len(cols) - 1
    date = rows[0][ti] if rows else None
    pts = [(row[li], row[oi], row[vi]) for row in rows if row[vi] is not None]
    return date, pts


def _with_gradient(pts, radius_nm):
    """Attach a local gradient (mean abs neighbour difference) to each point."""
    out = []
    for (la, lo, v) in pts:
        diffs = []
        for (la2, lo2, v2) in pts:
            if la2 == la and lo2 == lo:
                continue
            if _approx_nm(la, lo, la2, lo2) <= radius_nm:
                diffs.append(abs(v - v2))
        grad = sum(diffs) / len(diffs) if diffs else 0.0
        out.append({"lat": la, "lon": lo, "val": v, "grad": grad})
    return out


def _load_cache():
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_cache(cache):
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def fetch_sst():
    date, pts = _griddap("CRW_sst_v3_1", "analysed_sst", has_altitude=False)
    return {"source": "CRW CoralTemp 5km", "date": date,
            "grid": _with_gradient(pts, SST_RADIUS_NM)}


def fetch_chla():
    # Daily is freshest but cloud-gapped; weekly fills the gaps. Take whichever
    # gives usable coverage, preferring the freshest.
    best = None
    for ds, label in (("noaa_snpp_chla_daily", "VIIRS daily"),
                      ("noaa_snpp_chla_weekly", "VIIRS weekly")):
        try:
            date, pts = _griddap(ds, "chlor_a", has_altitude=True)
        except Exception:
            continue
        cand = {"source": label, "date": date, "grid": _with_gradient(pts, CHLA_RADIUS_NM),
                "n": len(pts)}
        if len(pts) >= MIN_CHLA_PIXELS:
            return cand
        if best is None or len(pts) > best["n"]:
            best = cand
    return best


def get_satellite():
    """Return {'sst': layer|None, 'chla': layer|None}. Each layer may carry
    'stale': True if it came from cache because the live fetch failed."""
    cache = _load_cache()
    result = {}
    for key, fn in (("sst", fetch_sst), ("chla", fetch_chla)):
        try:
            layer = fn()
            if layer and layer.get("grid"):
                layer["stale"] = False
                result[key] = layer
                cache[key] = layer
                continue
            raise RuntimeError("empty layer")
        except Exception as e:
            if key in cache:
                stale = dict(cache[key])
                stale["stale"] = True
                result[key] = stale
            else:
                result[key] = None
                result[key + "_error"] = str(e)
    _save_cache(cache)
    return result


def sample(layer, lat, lon):
    """Nearest grid point -> (value, gradient, distance_nm) or (None, None, None)."""
    if not layer or not layer.get("grid"):
        return None, None, None
    best, bd = None, 1e9
    for p in layer["grid"]:
        d = _approx_nm(lat, lon, p["lat"], p["lon"])
        if d < bd:
            bd, best = d, p
    if best is None:
        return None, None, None
    return best["val"], best["grad"], bd


def field_extent(layer):
    """(min,max,argmin_point,argmax_point) of the field, for 'where's the break'."""
    if not layer or not layer.get("grid"):
        return None
    g = layer["grid"]
    lo = min(g, key=lambda p: p["val"])
    hi = max(g, key=lambda p: p["val"])
    return {"min": lo["val"], "max": hi["val"], "cold": lo, "warm": hi}


if __name__ == "__main__":
    sat = get_satellite()
    for k in ("sst", "chla"):
        L = sat.get(k)
        if L:
            print(f"{k}: {L['source']} {L['date']} pts={len(L['grid'])} stale={L['stale']}")
            ext = field_extent(L)
            if ext:
                print(f"   range {ext['min']:.3f} .. {ext['max']:.3f}")
        else:
            print(f"{k}: UNAVAILABLE ({sat.get(k+'_error')})")
