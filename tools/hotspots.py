#!/usr/bin/env python3
"""Bait-likelihood hotspots = where birds & surface frenzies are MOST likely.

Scans the water near the home port and scores each cell on the three things that
concentrate bait (and therefore feeding tuna and working birds):
  * SST break   - thermal fronts stack bait               (NOAA CoralTemp 5 km)
  * chlorophyll - productive / colour edges = forage       (NOAA VIIRS)
  * current     - a moderate drift makes feeding seams      (Open-Meteo Marine)

Writes data/hotspots.json (top zones, de-clustered, WITH coordinates) which the
web map plots. This is a PREDICTION of where to look - not a fish detector.
Satellites can't see a live bust; run the coordinates, then find the white water
by watching for diving birds.

    PYTHONPATH=src python tools/hotspots.py
"""
from __future__ import annotations

import json
import math
import os

from tuna.sources._http import get_text, get_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ERDDAP = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap"

SEARCH_KM = 22.0        # how far from the marina to scan for hotspots
GRAD_KM = 7.0           # neighbourhood for the front / colour gradient
N_HOTSPOTS = 6
MIN_SEP_KM = 4.0        # de-cluster spacing
MIN_DEPTH_M = 25.0      # require >= 25 m of water: never land, never a shallow shoal


def km(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 111.0
    dlon = (lon2 - lon1) * 111.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(d):
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"][int((d + 11.25) % 360 // 22.5)]


def erddap_grid(dataset, var, has_alt, lat0, lat1, lon0, lon1):
    alt = "%5B0%5D" if has_alt else ""
    url = (f"{ERDDAP}/{dataset}.csv?{var}%5B(last)%5D{alt}"
           f"%5B({lat0}):({lat1})%5D%5B({lon0}):({lon1})%5D")
    txt = get_text(url, retries=3, timeout=60)
    lines = txt.strip().splitlines()
    cols = lines[0].split(",")
    li, oi, vi = cols.index("latitude"), cols.index("longitude"), len(cols) - 1
    date = None
    pts = []
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
    # attach local gradient
    for p in pts:
        diffs = [abs(p["val"] - q["val"]) for q in pts
                 if q is not p and km(p["lat"], p["lon"], q["lat"], q["lon"]) <= GRAD_KM]
        p["grad"] = sum(diffs) / len(diffs) if diffs else 0.0
    return date, pts


def etopo_depth_points(lat0, lat1, lon0, lon1):
    """ETOPO 2022 elevation grid (negative = metres below sea level). Land/water mask."""
    url = f"{ERDDAP}/ETOPO_2022_v1_15s.csv?z%5B({lat0}):({lat1})%5D%5B({lon0}):({lon1})%5D"
    lines = get_text(url, retries=3, timeout=60).strip().splitlines()
    cols = lines[0].split(",")
    li, oi, vi = cols.index("latitude"), cols.index("longitude"), len(cols) - 1
    pts = []
    for row in lines[2:]:
        f = row.split(",")
        try:
            pts.append({"lat": float(f[li]), "lon": float(f[oi]), "val": float(f[vi])})
        except (ValueError, IndexError):
            continue
    return pts


def nearest(pts, lat, lon, max_km=6.0):
    best, bd = None, 1e9
    for p in pts:
        d = km(lat, lon, p["lat"], p["lon"])
        if d < bd:
            bd, best = d, p
    return (best, bd) if best and bd <= max_km else (None, None)


def fetch_currents(points):
    lats = ",".join(f"{p['lat']:.3f}" for p in points)
    lons = ",".join(f"{p['lon']:.3f}" for p in points)
    url = (f"https://marine-api.open-meteo.com/v1/marine?latitude={lats}&longitude={lons}"
           f"&current=ocean_current_velocity,ocean_current_direction&timezone=auto")
    try:
        data = get_json(url, retries=2, timeout=40)
    except Exception:
        return [None] * len(points)
    if isinstance(data, dict):
        data = [data]
    return [d.get("current", {}).get("ocean_current_velocity") for d in data]


def front_score(grad):
    return max(0.0, min(1.0, grad / 0.12))          # ~0.12 C local break -> strong


def chla_score(val, grad):
    if val is None:
        return None
    if val < 0.05:
        prod = 0.3
    elif val <= 0.6:
        prod = 1.0
    elif val <= 1.5:
        prod = 0.7
    else:
        prod = 0.45
    edge = max(0.0, min(1.0, (grad or 0.0) / 0.10))
    return 0.5 * prod + 0.5 * edge


def current_score(kmh):
    if kmh is None:
        return None
    if kmh < 0.3:
        return 0.4
    if kmh <= 2.5:
        return 1.0
    if kmh <= 5.0:
        return 0.7
    return 0.45


def main():
    with open(os.path.join(ROOT, "data", "home.json"), encoding="utf-8") as f:
        home = json.load(f)
    hlat, hlon = home["lat"], home["lon"]
    dlat = SEARCH_KM / 111.0
    dlon = SEARCH_KM / (111.0 * math.cos(math.radians(hlat)))

    print("Scanning satellite SST + chlorophyll near Marina Dbayeh ...")
    sst_date, sst = erddap_grid("CRW_sst_v3_1", "analysed_sst", False,
                                hlat - dlat, hlat + dlat, hlon - dlon, hlon + 0.03)
    try:
        chl_date, chl = erddap_grid("noaa_snpp_chla_daily", "chlor_a", True,
                                    hlat - dlat, hlat + dlat, hlon - dlon, hlon + 0.03)
        if len(chl) < 6:
            chl_date, chl = erddap_grid("noaa_snpp_chla_weekly", "chlor_a", True,
                                        hlat - dlat, hlat + dlat, hlon - dlon, hlon + 0.03)
    except Exception:
        chl_date, chl = None, []

    # candidate cells = SST grid points within range, on the seaward side
    cands = [p for p in sst
             if km(hlat, hlon, p["lat"], p["lon"]) <= SEARCH_KM and p["lon"] <= hlon + 0.02]

    # HARD land/depth guard: keep only points with real offshore water beneath them
    try:
        depth_pts = etopo_depth_points(hlat - dlat, hlat + dlat, hlon - dlon, hlon + 0.03)
    except Exception:
        depth_pts = []
    if depth_pts:
        water = []
        for p in cands:
            dp, _ = nearest(depth_pts, p["lat"], p["lon"], max_km=1.5)
            if dp and dp["val"] <= -MIN_DEPTH_M:
                p["depth_m"] = int(round(-dp["val"]))
                water.append(p)
        cands = water

    currents = fetch_currents(cands)

    scored = []
    for p, cur in zip(cands, currents):
        cp, _ = nearest(chl, p["lat"], p["lon"]) if chl else (None, None)
        chl_v = cp["val"] if cp else None
        chl_g = cp["grad"] if cp else None
        f = front_score(p["grad"])
        c = chla_score(chl_v, chl_g)
        cu = current_score(cur)
        terms = [(f, 0.45)]
        if c is not None:
            terms.append((c, 0.35))
        if cu is not None:
            terms.append((cu, 0.20))
        wsum = sum(w for _, w in terms)
        score = sum(v * w for v, w in terms) / wsum
        why = [f"SST break {p['grad']:.2f}C"]
        if chl_v is not None:
            why.append(f"chl {chl_v:.2f}")
        if cur is not None:
            why.append(f"current {cur:.1f} km/h")
        scored.append({
            "lat": round(p["lat"], 4), "lon": round(p["lon"], 4),
            "score": round(score, 3), "sst_c": round(p["val"], 1),
            "depth_m": p.get("depth_m"),
            "sst_break_c": round(p["grad"], 2),
            "chl": round(chl_v, 2) if chl_v is not None else None,
            "current_kmh": round(cur, 1) if cur is not None else None,
            "dist_nm": round(km(hlat, hlon, p["lat"], p["lon"]) / 1.852, 1),
            "heading": compass(bearing(hlat, hlon, p["lat"], p["lon"])),
            "why": ", ".join(why),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    picks = []
    for s in scored:
        if all(km(s["lat"], s["lon"], q["lat"], q["lon"]) > MIN_SEP_KM for q in picks):
            picks.append(s)
        if len(picks) >= N_HOTSPOTS:
            break

    out = {
        "generated_utc_date": sst_date,
        "sst_source": f"NOAA CoralTemp 5km {sst_date}",
        "chl_source": f"NOAA VIIRS {chl_date}" if chl_date else "unavailable",
        "note": "Bait-likelihood prediction (SST break x chlorophyll x current) - where birds/frenzies "
                "are most likely. NOT a fish detector; confirm with diving birds on the water.",
        "hotspots": picks,
    }
    path = os.path.join(ROOT, "data", "hotspots.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(f"Saved {len(picks)} hotspots -> {path}")
    for i, s in enumerate(picks, 1):
        print(f"  {i}. {s['heading']} {s['dist_nm']}nm  ({s['lat']},{s['lon']})  "
              f"score {s['score']}  [{s['why']}]")


if __name__ == "__main__":
    main()
