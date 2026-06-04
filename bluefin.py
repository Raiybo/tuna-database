#!/usr/bin/env python3
"""
bluefin.py - Wide-area front finder for BIG bluefin off Marina Dbaye.

Coastal casting (tuna.py) covers ~5 nm for bonito/skipjack. Big bluefin are
different: they patrol the strong offshore TEMPERATURE BREAKS and the productive
(chlorophyll) edges along the shelf/canyon - usually well beyond casting range.

This scans a wide box of satellite SST + chlorophyll, finds where the sharpest
breaks line up with productive water, and reports those zones with a bearing and
distance from Dbaye so you know which way to run.

    python bluefin.py
"""

import json
import math
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ERDDAP = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap"

# Wide offshore box: out to ~45 nm W/SW/NW, into deep water past the shelf edge.
WIDE = {"lat0": 33.45, "lat1": 34.35, "lon0": 34.70, "lon1": 35.58}
GRAD_RADIUS_NM = 7.0
SHELF_NM = 4.0           # Lebanese shelf is narrow; past ~4 nm = deep canyon water


def approx_nm(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 60.0
    dlon = (lon2 - lon1) * 60.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dlat, dlon)


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(d):
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"][int((d + 11.25) % 360 // 22.5)]


def fetch(dataset, var, has_alt, attempts=4):
    box = f"%5B({WIDE['lat0']}):({WIDE['lat1']})%5D%5B({WIDE['lon0']}):({WIDE['lon1']})%5D"
    alt = "%5B0%5D" if has_alt else ""
    url = f"{ERDDAP}/{dataset}.json?{var}%5B(last)%5D{alt}{box}"
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tuna-bluefin/1.0"})
            with urllib.request.urlopen(req, timeout=70) as r:
                data = json.loads(r.read().decode("utf-8"))
            cols = data["table"]["columnNames"]
            rows = data["table"]["rows"]
            li, oi, vi = cols.index("latitude"), cols.index("longitude"), len(cols) - 1
            date = rows[0][cols.index("time")] if rows else None
            pts = [{"lat": rr[li], "lon": rr[oi], "val": rr[vi]} for rr in rows if rr[vi] is not None]
            return date, pts
        except Exception as e:
            last = e
    raise last


def with_gradient(pts, radius):
    for p in pts:
        diffs = [abs(p["val"] - q["val"]) for q in pts
                 if q is not p and approx_nm(p["lat"], p["lon"], q["lat"], q["lon"]) <= radius]
        p["grad"] = sum(diffs) / len(diffs) if diffs else 0.0
    return pts


def nearest(pts, lat, lon):
    best, bd = None, 1e9
    for p in pts:
        d = approx_nm(lat, lon, p["lat"], p["lon"])
        if d < bd:
            bd, best = d, p
    return best, bd


def main():
    with open(os.path.join(HERE, "spots.json"), encoding="utf-8") as f:
        home = json.load(f)["home"]
    hlat, hlon = home["lat"], home["lon"]

    print("Scanning wide offshore area for bluefin fronts ...")
    sdate, sst = fetch("CRW_sst_v3_1", "analysed_sst", False)
    sst = with_gradient(sst, GRAD_RADIUS_NM)

    cdate, chl = None, []
    for ds in ("noaa_snpp_chla_daily", "noaa_snpp_chla_weekly"):
        try:
            cdate, chl = fetch(ds, "chlor_a", True)
            chla_src = ds
            if len(chl) >= 20:
                break
        except Exception:
            continue

    smin = min(sst, key=lambda p: p["val"])
    smax = max(sst, key=lambda p: p["val"])
    gmax = max(p["grad"] for p in sst)

    print(f"\nSST {str(sdate)[:10]} (CoralTemp 5km):  {smin['val']:.1f}-{smax['val']:.1f} C across the area")
    print(f"  warmest water {smax['val']:.1f}C  {compass(bearing(hlat,hlon,smax['lat'],smax['lon']))} "
          f"{approx_nm(hlat,hlon,smax['lat'],smax['lon']):.0f} nm")
    print(f"  coolest water {smin['val']:.1f}C  {compass(bearing(hlat,hlon,smin['lat'],smin['lon']))} "
          f"{approx_nm(hlat,hlon,smin['lat'],smin['lon']):.0f} nm")
    if chl:
        print(f"Chlorophyll {str(cdate)[:10]} ({chla_src.split('_')[2]}): "
              f"{min(p['val'] for p in chl):.2f}-{max(p['val'] for p in chl):.2f} mg/m3 ({len(chl)} px)")

    # score each SST point as a bluefin zone: sharp break + productive edge + offshore
    ranked = []
    for p in sst:
        dist = approx_nm(hlat, hlon, p["lat"], p["lon"])
        front = min(100.0, p["grad"] / max(gmax, 1e-6) * 100.0)
        chla_v = chla_grad = None
        if chl:
            cp, cd = nearest(chl, p["lat"], p["lon"])
            if cd <= 6.0:
                chla_v, chla_grad = cp["val"], cp.get("grad")
        # productivity edge bonus (greener-than-blue desert, on an edge)
        prod = 0.0
        if chla_v is not None:
            prod = min(100.0, max(0.0, (chla_v - 0.06)) / 0.25 * 100.0)
        offshore = 1.0 if dist >= SHELF_NM else 0.4   # bluefin like the deep side
        score = (0.6 * front + 0.4 * prod) * offshore
        ranked.append({**p, "dist": dist, "front": front, "prod": prod,
                       "chla": chla_v, "score": score,
                       "brg": bearing(hlat, hlon, p["lat"], p["lon"])})

    ranked.sort(key=lambda x: x["score"], reverse=True)

    # de-cluster: keep hotspots at least ~4 nm apart
    picks = []
    for r in ranked:
        if all(approx_nm(r["lat"], r["lon"], q["lat"], q["lon"]) > 4.0 for q in picks):
            picks.append(r)
        if len(picks) >= 6:
            break

    print("\nLIKELY BLUEFIN ZONES (sharpest break x productive water):")
    for i, r in enumerate(picks, 1):
        chs = f", chl {r['chla']:.2f}" if r["chla"] is not None else ""
        reach = "castable" if r["dist"] <= 5.5 else "offshore run"
        print(f"  {i}. {compass(r['brg'])} {r['dist']:.0f} nm  ({r['lat']:.3f},{r['lon']:.3f})  "
              f"SST {r['val']:.1f}C, break {r['grad']:.2f}C{chs}   [{reach}]")

    out = os.path.join(HERE, "bluefin.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"sst_date": sdate, "chla_date": cdate, "zones": picks}, f, indent=1, default=str)
    print(f"\nSaved: {out}")
    print("Reminder: fronts get you to the zone - then hunt birds, bait balls and meter marks.")


if __name__ == "__main__":
    main()
