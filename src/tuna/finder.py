"""Gridded fish-finder: read the actual ocean structure, not just 11 marks.

Scans the water within range of the marina and scores every (de-clustered) cell
on the features that concentrate bait and therefore feeding bluefin:

  * SST front     - 1 km MUR thermal-gradient edges       (NOAA/JPL, fallback CoralTemp 5 km)
  * Chlorophyll   - productive anomaly + colour edges      (NOAA VIIRS)
  * Current edge  - shear/convergence between current cells (Open-Meteo Marine)
  * Structure     - shelf break / depth gradient            (ETOPO 2022)

Each cell gets a 0..1 score AND a confidence from MULTI-SIGNAL AGREEMENT: a spot
where the SST front, the colour edge and the current edge all line up is far more
trustworthy than one signal alone. Everything here is free / no-key.

A prediction of WHERE TO LOOK - not a fish detector. Run the coordinates and find
the white water by watching for diving birds.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from . import config, scoring, seasonality
from .conditions import bearing, compass
from .scoring import haversine_km as km
from .sources._http import get_json, get_text
from .spots import load_home

PFEG = "https://coastwatch.pfeg.noaa.gov/erddap"
OWATCH = "https://oceanwatch.pifsc.noaa.gov/erddap"


def _erddap_grid(host, dataset, var, has_alt, lat0, lat1, lon0, lon1, timeout=70):
    alt = "%5B0%5D" if has_alt else ""
    url = (f"{host}/griddap/{dataset}.csv?{var}%5B(last)%5D{alt}"
           f"%5B({lat0}):({lat1})%5D%5B({lon0}):({lon1})%5D")
    lines = get_text(url, retries=2, timeout=timeout).strip().splitlines()
    cols = lines[0].split(",")
    li, oi, vi = cols.index("latitude"), cols.index("longitude"), len(cols) - 1
    date, pts = None, []
    for row in lines[2:]:
        f = row.split(",")
        raw = f[vi].strip()
        if raw in ("", "NaN"):
            continue
        try:
            v = float(raw)
        except ValueError:
            continue
        if math.isnan(v):
            continue
        date = f[0][:10]
        pts.append({"lat": float(f[li]), "lon": float(f[oi]), "val": v})
    return date, pts


def _fetch_sst(b):
    """1 km MUR first (sharp fronts); fall back to 5 km CoralTemp."""
    try:
        d, p = _erddap_grid(PFEG, "jplMURSST41", "analysed_sst", False, *b)
        if len(p) >= 25:
            return "MUR 1km", d, p
    except Exception:
        pass
    d, p = _erddap_grid(OWATCH, "CRW_sst_v3_1", "analysed_sst", False, *b)
    return "CoralTemp 5km", d, p


def _fetch_chl(b):
    for ds in ("noaa_snpp_chla_daily", "noaa_snpp_chla_weekly"):
        try:
            d, p = _erddap_grid(OWATCH, ds, "chlor_a", True, *b)
            if len(p) >= 6:
                return f"VIIRS {ds.split('_')[-1]}", d, p
        except Exception:
            continue
    return None, None, []


def _fetch_depth(b):
    try:
        _, p = _erddap_grid(OWATCH, "ETOPO_2022_v1_15s", "z", False, *b)
        return p
    except Exception:
        return []


def _fetch_currents(cells):
    """Velocity + direction at each cell (chunked multi-location)."""
    out = []
    for i in range(0, len(cells), 100):
        chunk = cells[i:i + 100]
        lat = ",".join(f"{c['lat']:.3f}" for c in chunk)
        lon = ",".join(f"{c['lon']:.3f}" for c in chunk)
        url = (f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}"
               "&current=ocean_current_velocity,ocean_current_direction&timezone=auto")
        try:
            d = get_json(url, retries=2, timeout=45)
            d = d if isinstance(d, list) else [d]
        except Exception:
            d = [{}] * len(chunk)
        for x in d:
            cur = x.get("current", {}) if isinstance(x, dict) else {}
            vel = cur.get("ocean_current_velocity")
            ang = cur.get("ocean_current_direction")
            if vel is None or ang is None:
                out.append({"vel": vel, "u": None, "v": None})
            else:
                r = math.radians(ang)
                out.append({"vel": vel, "u": vel * math.sin(r), "v": vel * math.cos(r)})
    return out


class _Field:
    """Light spatial index over grid points for nearest / neighbourhood queries."""
    def __init__(self, pts):
        self.pts = pts

    def _near(self, lat, lon, r):
        return [p for p in self.pts if km(lat, lon, p["lat"], p["lon"]) <= r]

    def nearest(self, lat, lon, maxkm):
        best, bd = None, 1e9
        for p in self.pts:
            d = km(lat, lon, p["lat"], p["lon"])
            if d < bd:
                bd, best = d, p
        return best if best and bd <= maxkm else None

    def gradient(self, lat, lon, r):
        c = self.nearest(lat, lon, r)
        if not c:
            return 0.0
        near = [p for p in self._near(lat, lon, r) if p is not c]
        return (sum(abs(c["val"] - p["val"]) for p in near) / len(near)) if near else 0.0


def _clamp(x):
    return max(0.0, min(1.0, x))


def find(home=None) -> dict:
    home = home or load_home()
    hlat, hlon = home.lat, home.lon
    R = config.FINDER_SEARCH_KM
    dlat = R / 111.0
    dlon = R / (111.0 * math.cos(math.radians(hlat)))
    box = (hlat - dlat, hlat + dlat, hlon - dlon, hlon + 0.03)

    sst_src, sst_date, sst_pts = _fetch_sst(box)
    chl_src, chl_date, chl_pts = _fetch_chl(box)
    depth_pts = _fetch_depth(box)
    sst = _Field(sst_pts)
    chl = _Field(chl_pts) if chl_pts else None
    depth = _Field(depth_pts) if depth_pts else None
    chl_vals = [p["val"] for p in chl_pts] if chl_pts else []
    chl_median = sorted(chl_vals)[len(chl_vals) // 2] if chl_vals else None

    # candidate water cells: seaward, in range, real depth; subsample to a cap
    cands = [p for p in sst_pts
             if km(hlat, hlon, p["lat"], p["lon"]) <= R and p["lon"] <= hlon + 0.02]
    if depth:
        keep = []
        for p in cands:
            dp = depth.nearest(p["lat"], p["lon"], 2.0)
            if dp and dp["val"] <= -config.FINDER_MIN_DEPTH_M:
                p["depth_m"] = int(round(-dp["val"]))
                keep.append(p)
        cands = keep
    if len(cands) > config.FINDER_MAX_CELLS:
        stride = math.ceil(len(cands) / config.FINDER_MAX_CELLS)
        cands = cands[::stride]

    currents = _fetch_currents(cands)
    cur_field = [{"lat": c["lat"], "lon": c["lon"], **cu} for c, cu in zip(cands, currents)]

    scored = []
    g = config.FINDER_GRAD_KM
    for p, cu in zip(cands, currents):
        sst_front = _clamp(sst.gradient(p["lat"], p["lon"], g) / config.SST_FRONT_NORM)

        chl_v = chl_anom = chl_front = None
        if chl:
            cp = chl.nearest(p["lat"], p["lon"], 6.0)
            if cp:
                chl_v = cp["val"]
                chl_front = _clamp(chl.gradient(p["lat"], p["lon"], g) / config.CHL_FRONT_NORM)
                if chl_median and chl_median > 0:
                    chl_anom = _clamp(((chl_v - chl_median) / chl_median) / config.CHL_ANOM_NORM)

        # current edge = vector shear vs neighbouring current cells
        shear = None
        if cu.get("u") is not None:
            neigh = [q for q in cur_field
                     if q.get("u") is not None and 0 < km(p["lat"], p["lon"], q["lat"], q["lon"]) <= g]
            if neigh:
                shear = _clamp(sum(math.hypot(cu["u"] - q["u"], cu["v"] - q["v"])
                                   for q in neigh) / len(neigh) / config.CONVERGENCE_NORM)

        structure = None
        if depth:
            structure = _clamp(depth.gradient(p["lat"], p["lon"], g) / config.STRUCTURE_NORM)

        factors = {"sst_front": sst_front, "convergence": shear,
                   "chl_anom": chl_anom, "chl_front": chl_front, "structure": structure}
        score, contrib = scoring.combine_weighted(factors, config.FINDER_WEIGHTS)
        # Agreement counts INDEPENDENT data sources, not factors (chl_anom & chl_front
        # are both chlorophyll), so confidence isn't inflated by one source.
        chl_strength = max([x for x in (chl_anom, chl_front) if x is not None], default=None)
        sources = {"sst": sst_front, "chl": chl_strength,
                   "current": shear, "structure": structure}
        agree = [k for k, v in sources.items() if v is not None and v >= config.FINDER_STRONG]
        conf = "High" if len(agree) >= 3 else "Moderate" if len(agree) == 2 else "Low"

        why = []
        if sst_front >= config.FINDER_STRONG:
            why.append(f"SST front {sst.gradient(p['lat'], p['lon'], g):.2f}C")
        if shear and shear >= config.FINDER_STRONG:
            why.append("current edge")
        if chl_anom and chl_anom >= config.FINDER_STRONG:
            why.append(f"chl rich {chl_v:.2f}")
        if structure and structure >= config.FINDER_STRONG:
            why.append("shelf break")

        scored.append({
            "lat": round(p["lat"], 4), "lon": round(p["lon"], 4),
            "score": round(score, 3), "confidence": conf, "agree": len(agree),
            "signals": {k: round(v, 2) for k, v in contrib.items()},
            "sst_c": round(p["val"], 1),
            "chl": round(chl_v, 2) if chl_v is not None else None,
            "current_kmh": round(cu["vel"], 1) if cu.get("vel") is not None else None,
            "depth_m": p.get("depth_m"),
            "dist_nm": round(km(hlat, hlon, p["lat"], p["lon"]) / 1.852, 1),
            "heading": compass(bearing(hlat, hlon, p["lat"], p["lon"])),
            "why": ", ".join(why) or "weak signals",
        })

    # rank, then de-cluster
    scored.sort(key=lambda x: (x["score"], x["agree"]), reverse=True)
    picks = []
    for s in scored:
        if all(km(s["lat"], s["lon"], q["lat"], q["lon"]) > config.FINDER_MIN_SEP_KM for q in picks):
            picks.append(s)
        if len(picks) >= config.FINDER_N_HOTSPOTS:
            break

    season = seasonality.month_score(datetime.now(timezone.utc).month)
    return {
        "home": home.name,
        "generated_utc_date": sst_date,
        "sst_source": f"{sst_src} {sst_date}",
        "chl_source": f"{chl_src} {chl_date}" if chl_src else "unavailable",
        "cells_scored": len(cands),
        "season": seasonality.label(season),
        "season_score": round(season, 2),
        "note": "Multi-signal bait-likelihood (SST front x chlorophyll x current edge x structure). "
                "Confidence = how many signals agree. Prediction of where to look, NOT a fish "
                "detector - confirm with diving birds on the water.",
        "hotspots": picks,
    }
