#!/usr/bin/env python3
"""
Tuna - Daily tuna fishing forecast for Marina Dbaye, Lebanon.

Targets: bluefin, skipjack, bonito (any tuna). Method: jigging / casting, ~5 nm range.
Free data: Open-Meteo Marine + Weather APIs (no API key). Bite timing via `ephem` (solunar).

Run:  python tuna.py
Output:  report.html  (open it on your phone before you leave the dock)
"""

import json
import math
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

try:
    import ephem
    HAVE_EPHEM = True
except Exception:
    HAVE_EPHEM = False

import satellite

HERE = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
GRID_RADIUS_NM = 5.5          # how far offshore we scan
FORECAST_DAYS = 3             # today + 2 days outlook
SAFETY_WIND_KN = 20.0         # hard no-go above this
SAFETY_WAVE_M = 1.8           # hard no-go above this

NM_PER_DEG_LAT = 60.0         # 1 deg latitude = 60 nm


# ----------------------------------------------------------------------------
# Geo helpers
# ----------------------------------------------------------------------------
def nm_per_deg_lon(lat):
    return 60.0 * math.cos(math.radians(lat))


def haversine_nm(lat1, lon1, lat2, lon2):
    R = 3440.065  # nm
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(deg):
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) % 360 // 22.5)]


# ----------------------------------------------------------------------------
# Build the offshore scan grid (sea is to the W / NW / SW of Dbaye)
# ----------------------------------------------------------------------------
def build_grid(home_lat, home_lon):
    pts = []
    for dist in (1.5, 3.0, 4.5, 5.5):
        for brg in range(200, 341, 20):  # SSW through W to NNW
            rad = math.radians(brg)
            dlat = dist * math.cos(rad) / NM_PER_DEG_LAT
            dlon = dist * math.sin(rad) / nm_per_deg_lon(home_lat)
            pts.append((round(home_lat + dlat, 4), round(home_lon + dlon, 4)))
    return pts


# ----------------------------------------------------------------------------
# HTTP / data
# ----------------------------------------------------------------------------
def fetch_json(url, attempts=4):
    """Fetch with retry/backoff - public weather servers throw transient
    502 / SSL-EOF errors and one blip shouldn't crash the morning report."""
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tuna-forecast/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            if i < attempts - 1:
                print(f"  network hiccup ({type(e).__name__}), retrying in {2*(i+1)}s ...")
                time.sleep(2 * (i + 1))
    raise last


def fetch_weather(lat, lon):
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "hourly": "surface_pressure,wind_speed_10m,wind_direction_10m,wind_gusts_10m,cloud_cover",
        "daily": "sunrise,sunset",
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
        "wind_speed_unit": "kn",
    })
    return fetch_json("https://api.open-meteo.com/v1/forecast?" + q)


def fetch_marine_grid(points):
    lats = ",".join(str(p[0]) for p in points)
    lons = ",".join(str(p[1]) for p in points)
    q = urllib.parse.urlencode({
        "latitude": lats, "longitude": lons,
        "hourly": "wave_height,sea_surface_temperature,ocean_current_velocity,ocean_current_direction",
        "forecast_days": FORECAST_DAYS,
        "timezone": "auto",
    })
    data = fetch_json("https://marine-api.open-meteo.com/v1/marine?" + q)
    return data if isinstance(data, list) else [data]


# ----------------------------------------------------------------------------
# Scoring helpers (piecewise linear)
# ----------------------------------------------------------------------------
def lerp(x, x0, x1, y0, y1):
    if x <= x0:
        return y0
    if x >= x1:
        return y1
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def wind_score(kn):
    if kn <= 6:
        return 100.0
    if kn <= 10:
        return lerp(kn, 6, 10, 100, 80)
    if kn <= 14:
        return lerp(kn, 10, 14, 80, 50)
    if kn <= 18:
        return lerp(kn, 14, 18, 50, 15)
    return 8.0


def wave_score(m):
    if m <= 0.4:
        return 100.0
    if m <= 0.8:
        return lerp(m, 0.4, 0.8, 100, 75)
    if m <= 1.2:
        return lerp(m, 0.8, 1.2, 75, 45)
    if m <= 1.6:
        return lerp(m, 1.2, 1.6, 45, 15)
    return 5.0


def pressure_score(trend_6h, absolute):
    # Falling pressure (approaching weather) tends to switch the bite on.
    # Flat high pressure after a blow is usually slow.
    if trend_6h <= -6:
        s = 60          # crashing - likely rough/unsafe weather anyway
    elif trend_6h <= -1:
        s = 88          # gentle fall = feeding window
    elif trend_6h < 1:
        s = 70          # steady
    elif trend_6h < 3:
        s = 58          # rising
    else:
        s = 50          # fast rise after front
    if absolute > 1020:
        s -= 8          # strong high = often lock-jaw
    return max(0, min(100, s))


def current_score(kmh):
    if kmh < 0.3:
        return 30.0     # slack = bait scatters
    if kmh <= 3.5:
        return lerp(kmh, 0.3, 1.2, 60, 100)  # sweet spot
    if kmh <= 6:
        return lerp(kmh, 3.5, 6, 100, 45)
    return 35.0         # ripping current = hard to fish


def chla_band_score(mg):
    # Levantine water is a blue desert; tuna bait sits on productive EDGES, not
    # in the clear blue and not in the green turbid coastal soup.
    if mg < 0.05:
        return 40.0     # blue desert - little bait
    if mg <= 0.30:
        return lerp(mg, 0.05, 0.30, 60, 100)   # productive edge band - ideal
    if mg <= 0.80:
        return lerp(mg, 0.30, 0.80, 100, 70)
    return 50.0         # turbid/coastal - too green


def chla_score(mg, grad):
    if mg is None:
        return None
    abs_s = chla_band_score(mg)
    edge_s = min(100.0, (grad or 0.0) / 0.12 * 100.0)  # being on a colour edge
    return 0.5 * abs_s + 0.5 * edge_s


# ----------------------------------------------------------------------------
# Solunar (bite timing) via ephem
# ----------------------------------------------------------------------------
def solunar_for_day(lat, lon, day_date, utc_offset_sec):
    """Return list of (kind, local_datetime) major/minor periods centered on
    moon transit/antitransit (majors) and moonrise/moonset (minors)."""
    if not HAVE_EPHEM:
        return [], 50.0, 50.0
    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.elevation = 0
    obs.pressure = 0
    moon = ephem.Moon()

    local_midnight_utc = datetime(day_date.year, day_date.month, day_date.day) - timedelta(seconds=utc_offset_sec)
    end_utc = local_midnight_utc + timedelta(days=1)

    def to_local(ed):
        return ed.datetime() + timedelta(seconds=utc_offset_sec)

    events = []
    for kind, fn in (("major", "next_transit"),
                     ("major", "next_antitransit"),
                     ("minor", "next_rising"),
                     ("minor", "next_setting")):
        obs.date = ephem.Date(local_midnight_utc)
        try:
            ev = getattr(obs, fn)(moon)
            ev_utc = ev.datetime()
            if local_midnight_utc <= ev_utc < end_utc:
                events.append((kind, to_local(ev)))
        except Exception:
            pass

    obs.date = ephem.Date(local_midnight_utc + timedelta(hours=12))
    illum = ephem.Moon(obs).phase  # 0=new .. 100=full
    # Solunar force peaks at NEW and FULL moon.
    phase_strength = abs(illum - 50.0) / 50.0
    base = 50 + 30 * phase_strength
    return events, base, illum


def moon_phase_name(illum, waxing):
    if illum < 6:
        return "New moon"
    if illum > 94:
        return "Full moon"
    if illum < 45:
        return ("Waxing" if waxing else "Waning") + " crescent"
    if illum < 55:
        return ("First" if waxing else "Last") + " quarter"
    return ("Waxing" if waxing else "Waning") + " gibbous"


# ----------------------------------------------------------------------------
# Per-day analysis
# ----------------------------------------------------------------------------
def parse_iso(s):
    return datetime.fromisoformat(s)


def analyze_day(day_index, weather, marine_grid, spots, home, utc_offset_sec, sat):
    w = weather["hourly"]
    times = [parse_iso(t) for t in w["time"]]
    day0 = times[0].date() + timedelta(days=day_index)

    # indices belonging to this calendar day
    idx = [i for i, t in enumerate(times) if t.date() == day0]
    if not idx:
        return None

    sunrise = parse_iso(weather["daily"]["sunrise"][day_index])
    sunset = parse_iso(weather["daily"]["sunset"][day_index])

    # fishing window: dawn-30min .. dusk+30min
    fw_start = sunrise - timedelta(minutes=30)
    fw_end = sunset + timedelta(minutes=30)
    fw_idx = [i for i in idx if fw_start <= times[i] <= fw_end]
    if not fw_idx:
        fw_idx = idx

    winds = [w["wind_speed_10m"][i] for i in fw_idx]
    gusts = [w["wind_gusts_10m"][i] for i in fw_idx]
    press = [w["surface_pressure"][i] for i in idx]

    max_wind = max(winds)
    avg_wind = sum(winds) / len(winds)
    max_gust = max(gusts)

    # wave: from grid (use the cell nearest home / inshore average)
    waves_day = []
    for loc in marine_grid:
        wh = loc["hourly"]["wave_height"]
        waves_day += [wh[i] for i in fw_idx if i < len(wh) and wh[i] is not None]
    max_wave = max(waves_day) if waves_day else 0.0
    avg_wave = sum(waves_day) / len(waves_day) if waves_day else 0.0

    # pressure trend over middle of the day (6h)
    mid = len(idx) // 2
    a = press[max(0, mid - 3)]
    b = press[min(len(press) - 1, mid + 3)]
    trend6 = b - a
    abs_press = sum(press) / len(press)

    # solunar
    events, sol_base, moon_illum = solunar_for_day(home["lat"], home["lon"], day0, utc_offset_sec)
    # bonus if a major/minor overlaps low light (within 90 min of sunrise/sunset)
    overlap_bonus = 0
    for kind, t in events:
        for light in (sunrise, sunset):
            if abs((t - light).total_seconds()) <= 90 * 60:
                overlap_bonus = max(overlap_bonus, 20 if kind == "major" else 12)
    sol_score = min(100, sol_base + overlap_bonus)

    ws = wind_score(avg_wind)
    was = wave_score(max_wave)
    ps = pressure_score(trend6, abs_press)

    quality = 0.27 * ws + 0.22 * was + 0.18 * ps + 0.33 * sol_score

    # Go / No-Go
    if max_wind >= SAFETY_WIND_KN or max_wave >= SAFETY_WAVE_M:
        verdict, vclass = "NO-GO (unsafe)", "nogo"
    elif quality >= 70:
        verdict, vclass = "GO - Prime day", "prime"
    elif quality >= 56:
        verdict, vclass = "GO - Good", "good"
    elif quality >= 42:
        verdict, vclass = "Marginal", "marg"
    else:
        verdict, vclass = "Poor - only if keen", "poor"

    # ---- bite windows (hourly) ----
    windows = compute_windows(idx, times, w, marine_grid, fw_idx, sunrise, sunset, events)

    # ---- spot ranking (uses a representative hour) ----
    rep_i = fw_idx[0]
    # prefer first prime window's mid hour
    if windows:
        rep_dt = windows[0]["mid"]
        rep_i = min(idx, key=lambda i: abs((times[i] - rep_dt).total_seconds()))
    cells, your_spots = rank_spots(marine_grid, spots, home, rep_i, sat)

    # water summary (where's the break)
    sst_vals = [c["sst"] for c in cells if c.get("sst") is not None]
    warm = max((c for c in cells if c.get("sst") is not None), key=lambda c: c["sst"], default=None)
    cold = min((c for c in cells if c.get("sst") is not None), key=lambda c: c["sst"], default=None)
    chla_vals = [c["chla"] for c in cells if c.get("chla") is not None]

    return {
        "date": day0,
        "verdict": verdict,
        "vclass": vclass,
        "score": round(quality),
        "max_wind": round(max_wind, 1),
        "avg_wind": round(avg_wind, 1),
        "max_gust": round(max_gust, 1),
        "max_wave": round(max_wave, 2),
        "avg_wave": round(avg_wave, 2),
        "trend6": round(trend6, 1),
        "abs_press": round(abs_press),
        "sst_lo": min(sst_vals) if sst_vals else None,
        "sst_hi": max(sst_vals) if sst_vals else None,
        "warm": warm,
        "cold": cold,
        "chla_lo": min(chla_vals) if chla_vals else None,
        "chla_hi": max(chla_vals) if chla_vals else None,
        "sunrise": sunrise,
        "sunset": sunset,
        "moon_illum": moon_illum,
        "events": events,
        "sub": {"wind": round(ws), "wave": round(was), "pressure": round(ps), "solunar": round(sol_score)},
        "windows": windows,
        "cells": cells,
        "your_spots": your_spots,
        "rep_time": times[rep_i],
    }


def compute_windows(idx, times, w, marine_grid, fw_idx, sunrise, sunset, events):
    def in_period(t):
        for kind, et in events:
            half = 90 if kind == "major" else 45
            if abs((t - et).total_seconds()) <= half * 60:
                return kind
        return None

    # mean wave per hour across grid
    def hour_wave(i):
        vals = [loc["hourly"]["wave_height"][i] for loc in marine_grid
                if i < len(loc["hourly"]["wave_height"]) and loc["hourly"]["wave_height"][i] is not None]
        return sum(vals) / len(vals) if vals else 0.0

    hours = []
    for i in fw_idx:
        t = times[i]
        wind = w["wind_speed_10m"][i]
        wave = hour_wave(i)
        ok = wind <= 16 and wave <= 1.5
        near_light = min(abs((t - sunrise).total_seconds()),
                         abs((t - sunset).total_seconds())) <= 90 * 60
        per = in_period(t)
        light_f = 1.0 if near_light else 0.45
        sol_f = 1.0 if per == "major" else (0.7 if per == "minor" else 0.35)
        bite = (0.5 * light_f + 0.5 * sol_f) * 100 if ok else 12
        reasons = []
        if near_light:
            reasons.append("low light")
        if per:
            reasons.append("solunar " + per)
        hours.append({"i": i, "t": t, "bite": bite, "ok": ok, "reasons": reasons})

    # group consecutive hours with bite >= 60
    windows = []
    cur = None
    for h in hours:
        if h["bite"] >= 60:
            if cur is None:
                cur = {"start": h["t"], "end": h["t"], "max": h["bite"], "reasons": set(h["reasons"])}
            else:
                cur["end"] = h["t"]
                cur["max"] = max(cur["max"], h["bite"])
                cur["reasons"].update(h["reasons"])
        else:
            if cur:
                windows.append(cur)
                cur = None
    if cur:
        windows.append(cur)

    for win in windows:
        win["end"] = win["end"] + timedelta(hours=1)
        win["mid"] = win["start"] + (win["end"] - win["start"]) / 2
        win["reasons"] = ", ".join(sorted(win["reasons"])) or "best light/feed overlap"
    windows.sort(key=lambda x: x["max"], reverse=True)
    return windows[:3]


def rank_spots(marine_grid, spots, home, rep_i, sat):
    """Rank candidate spots using the high-res satellite SST/chla fields plus the
    Open-Meteo current/wave forecast and the user's own structure marks."""
    sat_sst = sat.get("sst")
    sat_chla = sat.get("chla")

    # Open-Meteo current/wave snapshot per cell, for nearest-lookup.
    omcells = []
    for loc in marine_grid:
        h = loc["hourly"]
        if rep_i >= len(h["ocean_current_velocity"]):
            continue
        omcells.append({
            "lat": loc["latitude"], "lon": loc["longitude"],
            "cur": h["ocean_current_velocity"][rep_i] or 0.0,
            "cur_dir": h["ocean_current_direction"][rep_i] or 0.0,
            "wave": h["wave_height"][rep_i] if rep_i < len(h["wave_height"]) else None,
        })

    def nearest_om(lat, lon):
        if not omcells:
            return 0.0, 0.0, None
        c = min(omcells, key=lambda c: haversine_nm(lat, lon, c["lat"], c["lon"]))
        return c["cur"], c["cur_dir"], c["wave"]

    structures = [s for s in spots if s.get("type") in ("dropoff", "reef", "wreck", "structure")]

    def score_point(lat, lon):
        sst, sst_grad, _ = satellite.sample(sat_sst, lat, lon)
        chla, chla_grad, chla_d = satellite.sample(sat_chla, lat, lon)
        if chla_d is not None and chla_d > 5.0:   # nearest valid chl pixel too far
            chla = chla_grad = None
        cur, cur_dir, wave = nearest_om(lat, lon)
        front = min(100.0, (sst_grad or 0.0) / 0.20 * 100.0)   # 0.20 C local break -> strong
        cs = current_score(cur)
        chs = chla_score(chla, chla_grad)
        nd = ss = None
        if structures:
            nd = min(haversine_nm(lat, lon, s["lat"], s["lon"]) for s in structures)
            ss = lerp(nd, 0.5, 3.0, 100, 0)
        terms = [(front, 0.34)]
        if chs is not None:
            terms.append((chs, 0.24))
        terms.append((cs, 0.22))
        if ss is not None:
            terms.append((ss, 0.20))
        wsum = sum(w for _, w in terms)
        total = sum(v * w for v, w in terms) / wsum
        return {"sst": sst, "sst_grad": sst_grad or 0.0, "chla": chla, "chla_grad": chla_grad,
                "cur": cur, "cur_dir": cur_dir, "wave": wave,
                "near_struct_nm": nd, "score": round(total)}

    def make(lat, lon):
        sc = score_point(lat, lon)
        d = haversine_nm(home["lat"], home["lon"], lat, lon)
        sc.update({"lat": lat, "lon": lon, "dist_nm": round(d, 1),
                   "brg": round(bearing_deg(home["lat"], home["lon"], lat, lon))})
        return sc

    # Candidate spots = satellite SST grid points within range, on the seaward side.
    cells = []
    if sat_sst and sat_sst.get("grid"):
        for p in sat_sst["grid"]:
            d = haversine_nm(home["lat"], home["lon"], p["lat"], p["lon"])
            if d <= GRID_RADIUS_NM and p["lon"] <= home["lon"] + 0.01:
                cells.append(make(p["lat"], p["lon"]))
    if not cells:  # fallback to the Open-Meteo grid if satellite is unavailable
        for c in omcells:
            d = haversine_nm(home["lat"], home["lon"], c["lat"], c["lon"])
            if d <= GRID_RADIUS_NM:
                cells.append(make(c["lat"], c["lon"]))
    cells.sort(key=lambda x: x["score"], reverse=True)

    # Rank the user's own marks by today's conditions.
    your = []
    for s in spots:
        if s.get("type") == "departure":
            continue
        m = make(s["lat"], s["lon"])
        m.update({"name": s["name"], "type": s.get("type", "spot"), "depth_m": s.get("depth_m")})
        your.append(m)
    your.sort(key=lambda x: x["score"], reverse=True)
    return cells, your


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def fmt_t(dt):
    return dt.strftime("%H:%M")


def gmap(lat, lon):
    return f"https://www.google.com/maps?q={lat:.4f},{lon:.4f}"


def why_text(day):
    s = day["sub"]
    bits = []
    if s["wind"] >= 75:
        bits.append("light wind")
    elif s["wind"] >= 45:
        bits.append("workable wind")
    else:
        bits.append(f"strong wind (gusts {day['max_gust']} kn)")
    if s["wave"] >= 70:
        bits.append("calm sea")
    elif s["wave"] < 45:
        bits.append(f"lumpy sea (to {day['max_wave']} m)")
    if day["trend6"] <= -1:
        bits.append(f"falling pressure ({day['trend6']} hPa) — feeding")
    elif day["trend6"] >= 2:
        bits.append("rising pressure — slower bite")
    if day["sub"]["solunar"] >= 75:
        bits.append("strong solunar timing")
    return ", ".join(bits)


# ----------------------------------------------------------------------------
# Logbook  (learn which conditions actually catch fish for YOU)
# ----------------------------------------------------------------------------
LOGBOOK = os.path.join(HERE, "logbook.json")
SPECIES = {"bluefin", "tuna", "skipjack", "bonito", "albacore", "tunny",
           "littletunny", "palamida", "amberjack", "leerfish", "mahi"}


def load_logbook():
    if os.path.exists(LOGBOOK):
        try:
            with open(LOGBOOK, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_logbook(entries):
    with open(LOGBOOK, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=1)


def day_features(day):
    """The condition fingerprint we match trips on."""
    return {
        "score": float(day["score"]),
        "sst_spread": float((day["sst_hi"] - day["sst_lo"]) if day["sst_hi"] is not None else 0.0),
        "chla": float(day["chla_hi"] if day["chla_hi"] is not None else 0.0),
        "solunar": float(day["sub"]["solunar"]),
        "wind": float(day["avg_wind"]),
        "moon": float(day.get("moon_illum", 50.0)),
    }


def analyze_logbook(today):
    entries = load_logbook()
    out = {"n": len(entries), "recent": list(reversed(entries[-3:]))}
    prod = [e for e in entries if e.get("productive") and e.get("features")]
    out["n_prod"] = len(prod)
    if len(prod) >= 3:
        import statistics
        feats = ["score", "sst_spread", "chla", "solunar", "wind", "moon"]
        means = {f: statistics.mean(e["features"][f] for e in prod) for f in feats}
        stds = {f: (statistics.pstdev([e["features"][f] for e in prod]) or 1.0) for f in feats}
        tf = day_features(today)
        close = [max(0.0, 1 - abs(tf[f] - means[f]) / (2 * stds[f] + 1e-6)) for f in feats]
        out["match"] = round(100 * sum(close) / len(close))
        out["means"] = means
    return out


def build_report(days, home, generated_local):
    today = days[0]

    def chip(label, val, good):
        cls = "g" if good else "b"
        return f'<span class="chip {cls}">{label}: {val}</span>'

    win_html = ""
    if today["windows"]:
        for win in today["windows"]:
            win_html += (f'<div class="win"><div class="wt">{fmt_t(win["start"])}–{fmt_t(win["end"])}</div>'
                         f'<div class="wr">{win["reasons"]}</div></div>')
    else:
        win_html = '<div class="muted">No standout window — fish dawn (best light) and watch for working birds.</div>'

    def detail(c):
        bits = []
        if c.get("sst") is not None:
            bits.append(f'SST {c["sst"]:.1f}°C')
        if c.get("sst_grad"):
            bits.append(f'break {c["sst_grad"]:.2f}°C')
        if c.get("chla") is not None:
            bits.append(f'chl {c["chla"]:.2f}')
        bits.append(f'cur {c["cur"]:.1f} km/h {compass(c["cur_dir"])}')
        if c.get("near_struct_nm") is not None:
            bits.append(f'{c["near_struct_nm"]:.1f} nm off structure')
        return " · ".join(bits)

    # top spots = best satellite grid cells
    spot_html = ""
    for c in today["cells"][:3]:
        spot_html += (
            f'<a class="spot" href="{gmap(c["lat"], c["lon"])}" target="_blank">'
            f'<div class="srow"><b>{compass(c["brg"])} · {c["dist_nm"]} nm</b><span class="sc">{c["score"]}</span></div>'
            f'<div class="sg">{c["lat"]:.4f}, {c["lon"]:.4f}</div>'
            f'<div class="muted">{detail(c)}</div>'
            f'</a>')

    # your spots ranked
    your_html = ""
    for s in today["your_spots"]:
        your_html += (
            f'<a class="spot" href="{gmap(s["lat"], s["lon"])}" target="_blank">'
            f'<div class="srow"><b>{s["name"]}</b><span class="sc">{s["score"]}</span></div>'
            f'<div class="muted">{compass(s["brg"])} · {s["dist_nm"]} nm · {detail(s)}</div>'
            f'</a>')

    # satellite water card
    sat = today.get("sat", {})
    sst_L, chla_L = sat.get("sst"), sat.get("chla")
    water_bits = []
    if today.get("warm") and today.get("cold") and today["sst_hi"] is not None:
        w, c = today["warm"], today["cold"]
        spread = today["sst_hi"] - today["sst_lo"]
        if spread >= 0.15:
            water_bits.append(
                f'<div class="muted">Temperature break: warm side <b>{today["sst_hi"]:.1f}°C</b> '
                f'to the {compass(w["brg"])}, cool side <b>{today["sst_lo"]:.1f}°C</b> to the {compass(c["brg"])} '
                f'(<b>{spread:.1f}°C</b> spread). Work the edge between them.</div>')
        else:
            water_bits.append(f'<div class="muted">Water is uniform (~{today["sst_hi"]:.1f}°C, no strong break today) — '
                              f'lean on current, structure and bird activity.</div>')
    if today.get("chla_hi") is not None:
        lvl = "productive" if today["chla_hi"] >= 0.2 else "clear/blue"
        water_bits.append(f'<div class="muted">Chlorophyll {today["chla_lo"]:.2f}–{today["chla_hi"]:.2f} mg/m³ ({lvl}). '
                          f'Greener edges = bait.</div>')
    src = []
    if sst_L:
        src.append(f'SST {sst_L["source"]} {str(sst_L["date"])[:10]}' + (' (cached)' if sst_L.get("stale") else ''))
    if chla_L:
        src.append(f'chl {chla_L["source"]} {str(chla_L["date"])[:10]}' + (' (cached)' if chla_L.get("stale") else ''))
    water_html = "".join(water_bits) + (f'<div class="src">{" · ".join(src)}</div>' if src else "")

    # logbook card
    lb = today.get("logbook") or {"n": 0}
    lb_html = ""
    if lb.get("match") is not None:
        m = lb["match"]
        cls = "g" if m >= 65 else ("n" if m >= 45 else "b")
        means = lb["means"]
        lb_html += (f'<div class="srow"><b>Today matches your good days</b>'
                    f'<span class="chip {cls}" style="font-size:14px">{m}%</span></div>')
        lb_html += (f'<div class="muted" style="margin-top:6px">Your fish came on: '
                    f'moon ~{means["moon"]:.0f}% lit · SST break ~{means["sst_spread"]:.1f}°C · '
                    f'wind ~{means["wind"]:.0f} kn · day-score ~{means["score"]:.0f} '
                    f'(from {lb["n_prod"]} productive trips).</div>')
    elif lb.get("n"):
        need = max(0, 3 - lb.get("n_prod", 0))
        lb_html += (f'<div class="muted">{lb["n"]} trip(s) logged. '
                    f'Log {need} more productive trip(s) and I\'ll start matching today to your best days.</div>')
    else:
        lb_html += ('<div class="muted">No trips logged yet. After a trip, run:<br>'
                    '<b>python tuna.py log bonito 3</b> &nbsp;(species + how many)</div>')
    for e in lb.get("recent", []):
        catch = (", ".join(e.get("species", [])) or e.get("quality", "fished"))
        cnt = f' ×{e["count"]}' if e.get("count") else ""
        sc = e.get("features", {}).get("score")
        sc_txt = f'score {sc:.0f}' if isinstance(sc, (int, float)) else ""
        lb_html += (f'<div class="logrow"><span>{e["date"]} · {catch}{cnt}</span>'
                    f'<span class="muted">{sc_txt}</span></div>')

    # solunar list
    ev_html = ""
    for kind, t in sorted(today["events"], key=lambda e: e[1]):
        ev_html += f'<span class="chip {"g" if kind=="major" else "n"}">{kind} {fmt_t(t)}</span>'
    if not ev_html:
        ev_html = '<span class="muted">solunar n/a</span>'

    # outlook
    out_html = ""
    for d in days:
        out_html += (
            f'<tr class="{d["vclass"]}"><td>{d["date"].strftime("%a %d")}</td>'
            f'<td><b>{d["score"]}</b></td><td>{d["verdict"].split(" (")[0]}</td>'
            f'<td>{d["avg_wind"]}kn</td><td>{d["max_wave"]}m</td></tr>')

    sst_range = ""
    if today["sst_lo"] is not None:
        sst_range = f'{today["sst_lo"]:.1f}–{today["sst_hi"]:.1f}°C'

    html = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Tuna · Dbaye</title>
<style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0a1622;color:#e8f0f7;padding:14px;max-width:560px;margin:0 auto}}
h1{{font-size:18px;margin:0 0 2px}}
.sub{{color:#7d97ad;font-size:12px;margin-bottom:14px}}
.banner{{border-radius:16px;padding:16px;margin-bottom:14px;display:flex;align-items:center;gap:14px}}
.banner .score{{font-size:42px;font-weight:800;line-height:1}}
.banner .v{{font-size:17px;font-weight:700}}
.banner .vd{{font-size:12px;opacity:.85;margin-top:3px}}
.prime{{background:linear-gradient(135deg,#0c5e2f,#0f7d3e)}}
.good{{background:linear-gradient(135deg,#0c4a5e,#137a8c)}}
.marg{{background:linear-gradient(135deg,#5e4a0c,#8c7013)}}
.poor{{background:linear-gradient(135deg,#5e2a0c,#8c4313)}}
.nogo{{background:linear-gradient(135deg,#5e0c1a,#8c1326)}}
.card{{background:#11243a;border-radius:14px;padding:13px 14px;margin-bottom:12px}}
.card h2{{font-size:13px;text-transform:uppercase;letter-spacing:.5px;color:#7d97ad;margin:0 0 10px}}
.win{{display:flex;justify-content:space-between;align-items:baseline;padding:8px 0;border-bottom:1px solid #1c3450}}
.win:last-child{{border:0}}
.wt{{font-size:18px;font-weight:700}}
.wr{{font-size:12px;color:#9fb6cc;text-align:right}}
.spot{{display:block;text-decoration:none;color:inherit;background:#0d1d30;border:1px solid #1c3450;border-radius:10px;padding:10px 12px;margin-bottom:8px}}
.srow{{display:flex;justify-content:space-between;align-items:center}}
.srow b{{font-size:15px}}
.sc{{background:#16385a;border-radius:8px;padding:2px 9px;font-weight:700;font-size:14px}}
.sg{{font-size:12px;color:#5fa8e0;margin:2px 0}}
.muted{{font-size:12px;color:#8aa3ba;line-height:1.45}}
.src{{font-size:10px;color:#5d7790;margin-top:8px}}
.logrow{{display:flex;justify-content:space-between;font-size:12px;padding:6px 0;border-bottom:1px solid #1c3450}}
.logrow:last-child{{border:0}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chip{{font-size:11px;padding:3px 9px;border-radius:20px;background:#16283f}}
.chip.g{{background:#13402a;color:#7fe0a8}}
.chip.b{{background:#40161c;color:#e69aa6}}
.chip.n{{background:#1c3450;color:#9fb6cc}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
td{{padding:7px 4px;border-bottom:1px solid #1c3450}}
tr.prime td:nth-child(2){{color:#5fe08f}}
tr.nogo td:nth-child(2){{color:#e6788a}}
.why{{font-size:13px;line-height:1.5;color:#c8d8e6}}
.foot{{font-size:11px;color:#5d7790;margin-top:16px;line-height:1.5}}
</style></head><body>

<h1>🎣 Tuna · Marina Dbaye</h1>
<div class="sub">{today['date'].strftime('%A %d %B %Y')} · updated {fmt_t(generated_local)} · ☀ {fmt_t(today['sunrise'])}–{fmt_t(today['sunset'])}</div>

<div class="banner {today['vclass']}">
  <div class="score">{today['score']}</div>
  <div><div class="v">{today['verdict']}</div>
  <div class="vd">{why_text(today)}</div></div>
</div>

<div class="card">
  <h2>Best bite windows today</h2>
  {win_html}
  <div class="chips" style="margin-top:10px">{ev_html}</div>
</div>

<div class="card">
  <h2>Water now &nbsp;<span class="muted">satellite</span></h2>
  {water_html}
</div>

<div class="card">
  <h2>Where to fish today &nbsp;<span class="muted">SST {sst_range}</span></h2>
  {spot_html}
  <div class="muted" style="margin-top:4px">Tap a spot to open it in Maps. Work the temperature break edge and watch for diving birds / surface busts.</div>
</div>

<div class="card">
  <h2>Your marks, ranked for today</h2>
  {your_html if your_html else '<div class="muted">Add your real GPS marks to spots.json.</div>'}
</div>

<div class="card">
  <h2>Conditions</h2>
  <div class="chips">
    {chip('Wind', str(today['avg_wind'])+' kn (gust '+str(today['max_gust'])+')', today['sub']['wind']>=55)}
    {chip('Sea', str(today['max_wave'])+' m', today['sub']['wave']>=55)}
    {chip('Pressure', str(today['abs_press'])+' hPa ('+('+' if today['trend6']>=0 else '')+str(today['trend6'])+')', today['sub']['pressure']>=60)}
    {chip('Solunar', str(today['sub']['solunar'])+'/100', today['sub']['solunar']>=65)}
  </div>
</div>

<div class="card">
  <h2>Logbook &nbsp;<span class="muted">learns your water</span></h2>
  {lb_html}
</div>

<div class="card">
  <h2>3-day outlook</h2>
  <table>
    <tr><td><b>Day</b></td><td><b>Score</b></td><td><b>Call</b></td><td><b>Wind</b></td><td><b>Sea</b></td></tr>
    {out_html}
  </table>
</div>

<div class="foot">
Free data: Open-Meteo Marine + Weather. Bite timing: solunar (moon transit/rise). Scores are guidance, not a guarantee — <b>always check official marine weather and your own judgement before going out.</b> Sea conditions can change fast.
</div>
</body></html>"""
    return html


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def gather(quiet=False):
    """Fetch everything and analyse the forecast days. Shared by the report and
    the logbook command."""
    with open(os.path.join(HERE, "spots.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    home = cfg["home"]
    spots = cfg["spots"]

    if not quiet:
        print("Fetching weather + marine forecast for Marina Dbaye ...")
    grid_points = build_grid(home["lat"], home["lon"])
    weather = fetch_weather(home["lat"], home["lon"])
    marine = fetch_marine_grid(grid_points)
    utc_offset = weather.get("utc_offset_seconds", 0)

    if not quiet:
        print("Fetching satellite ocean state (SST + chlorophyll) ...")
    sat = satellite.get_satellite()
    if not quiet:
        for k in ("sst", "chla"):
            L = sat.get(k)
            if L:
                print(f"  {k}: {L['source']} {str(L['date'])[:10]} "
                      f"({len(L['grid'])} px{', STALE/cache' if L.get('stale') else ''})")
            else:
                print(f"  {k}: unavailable")

    generated_local = datetime.utcnow() + timedelta(seconds=utc_offset)
    days = []
    for di in range(FORECAST_DAYS):
        d = analyze_day(di, weather, marine, spots, home, utc_offset, sat)
        if d:
            days.append(d)
    days[0]["sat"] = sat
    return {"days": days, "home": home, "spots": spots, "generated": generated_local}


def main():
    data = gather()
    days, home = data["days"], data["home"]
    days[0]["logbook"] = analyze_logbook(days[0])

    html = build_report(days, home, data["generated"])
    out = os.path.join(HERE, "report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    t = days[0]
    print(f"\n  {t['date']}  ->  {t['verdict']}   score {t['score']}/100")
    print(f"  wind {t['avg_wind']}kn (gust {t['max_gust']})  sea {t['max_wave']}m  "
          f"pressure {t['abs_press']}hPa ({t['trend6']:+})")
    if t["windows"]:
        print("  bite windows: " + ", ".join(f"{fmt_t(w['start'])}-{fmt_t(w['end'])}" for w in t["windows"]))
    if t["cells"] and t["cells"][0].get("sst") is not None:
        c = t["cells"][0]
        print(f"  top spot: {compass(c['brg'])} {c['dist_nm']}nm  ({c['lat']:.4f},{c['lon']:.4f})  "
              f"SST {c['sst']:.1f}C  score {c['score']}")
    lb = days[0]["logbook"]
    if lb.get("match") is not None:
        print(f"  logbook match: {lb['match']}% of your good days")
    print(f"\nReport written: {out}")


def cmd_log(args):
    """Dead-simple trip logger:  python tuna.py log <species|good|blank> [count] [notes...]
       Examples:  log bonito 3      log skipjack 2 birds off the point      log blank"""
    species, count, quality, notes = [], None, None, []
    for tok in args:
        low = tok.lower()
        if low.isdigit():
            count = int(low)
        elif low in ("blank", "skunked", "nothing", "none", "zero"):
            quality = "blank"
        elif low in ("good", "great", "slow", "ok", "fished"):
            quality = low
        elif low in SPECIES:
            species.append(low)
        elif not species and quality is None and not notes:
            species.append(low)        # first free word = species name
        else:
            notes.append(tok)

    print("Stamping today's conditions ...")
    data = gather(quiet=True)
    today = data["days"][0]

    productive = bool((count and count > 0) or (species and quality != "blank")
                      or quality in ("good", "great"))
    entry = {
        "date": str(today["date"]),
        "logged_at": data["generated"].strftime("%Y-%m-%d %H:%M"),
        "species": species,
        "count": count,
        "quality": quality or ("catch" if productive else "fished"),
        "productive": productive,
        "notes": " ".join(notes),
        "spot": ({"lat": today["cells"][0]["lat"], "lon": today["cells"][0]["lon"]}
                 if today["cells"] else None),
        "features": day_features(today),
        "verdict": today["verdict"],
    }
    entries = load_logbook()
    entries.append(entry)
    save_logbook(entries)

    what = (", ".join(species) or entry["quality"])
    cnt = f" x{count}" if count else ""
    f = entry["features"]
    print(f"\n  Logged: {what}{cnt} on {entry['date']}  ({'fish' if productive else 'no fish'})")
    print(f"  conditions: score {f['score']:.0f}, SST break {f['sst_spread']:.1f}C, "
          f"moon {f['moon']:.0f}%, wind {f['wind']:.0f}kn")
    print(f"  logbook now holds {len(entries)} trip(s). Run 'python tuna.py' to see the updated report.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "log":
        cmd_log(sys.argv[2:])
    else:
        main()
