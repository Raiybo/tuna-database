#!/usr/bin/env python3
"""Render the daily tuna day-sheet as ONE shareable PNG (phone / WhatsApp).

Pulls the live model (`python -m tuna --json`), then paints a poster: verdict,
conditions, bite windows, and the best in-range spots WITH exact GPS coordinates,
over a real stitched mini-map. Honest scout note at the foot.

    PYTHONPATH=src python tools/day_image.py
    -> docs/day-<date>.png   and   docs/day.png (latest)
"""
from __future__ import annotations

import io
import json
import math
import os
import subprocess
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

W = 1080
BG = (9, 20, 32)
CARD = (17, 36, 58)
EDGE = (28, 52, 80)
INK = (233, 240, 247)
SUB = (138, 163, 186)
VCOL = {"GO": (15, 125, 62), "DECENT": (19, 122, 140), "MARGINAL": (140, 112, 19),
        "SLOW": (120, 80, 30), "TOUGH": (150, 26, 44)}
RCOL = {"PRIME": (26, 152, 80), "GOOD": (145, 207, 96), "FAIR": (253, 174, 97), "POOR": (215, 70, 60)}


def font(size, bold=False):
    for c in ([r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"] if bold
              else [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]) + \
             (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"] if bold
              else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]):
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


F = {"h1": font(46, True), "h2": font(26, True), "big": font(74, True), "v": font(40, True),
     "b": font(30, True), "m": font(27), "s": font(23), "xs": font(20), "mono": font(26, True)}


_PHASE_SHORT = {"New Moon": "New", "Waxing Crescent": "Wax Cr", "First Quarter": "1st Qtr",
                "Waxing Gibbous": "Wax Gib", "Full Moon": "Full", "Waning Gibbous": "Wan Gib",
                "Last Quarter": "Last Qtr", "Waning Crescent": "Wan Cr"}


def _short_phase(p):
    return _PHASE_SHORT.get(p, p)


def get_report():
    env = dict(os.environ, PYTHONPATH="src")
    out = subprocess.check_output([sys.executable, "-m", "tuna", "--json"], cwd=ROOT, env=env)
    return json.loads(out.decode("utf-8"))


# ---- web mercator tile helpers ----
def deg2xy(lat, lon, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def static_map(center, span, size, z=10):
    clat, clon = center
    nw = deg2xy(clat + span, clon - span, z)
    se = deg2xy(clat - span, clon + span, z)
    tx0, tx1 = int(math.floor(nw[0])), int(math.floor(se[0]))
    ty0, ty1 = int(math.floor(nw[1])), int(math.floor(se[1]))
    canvas = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256), (14, 26, 38))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            try:
                url = f"https://a.basemaps.cartocdn.com/dark_all/{z}/{tx}/{ty}.png"
                req = urllib.request.Request(url, headers={"User-Agent": "tuna/1.0"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    tile = Image.open(io.BytesIO(r.read())).convert("RGB")
                canvas.paste(tile, ((tx - tx0) * 256, (ty - ty0) * 256))
            except Exception:
                pass
    left = (nw[0] - tx0) * 256
    top = (nw[1] - ty0) * 256
    right = (se[0] - tx0) * 256
    bot = (se[1] - ty0) * 256
    crop = canvas.crop((int(left), int(top), int(right), int(bot))).resize(size)

    def to_px(lat, lon):
        x, y = deg2xy(lat, lon, z)
        cx = ((x - tx0) * 256 - left) / (right - left) * size[0]
        cy = ((y - ty0) * 256 - top) / (bot - top) * size[1]
        return cx, cy

    return crop, to_px


def rrect(d, box, r, fill):
    d.rounded_rectangle(box, radius=r, fill=fill)


def text(d, xy, s, f, fill=INK, anchor="la"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def wrap(d, s, f, maxw):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build(rep):
    home = rep["home"]
    oc = rep["ocean"]
    mn = rep["moon"]
    date = rep["as_of"][:10]

    # choose spots to feature: in-range first by score, then nearest out-of-range
    spots = rep["spots"]
    inr = [s for s in spots if s.get("in_range")]
    pick = (inr or spots)[:4]

    H = 2360
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    pad = 40
    y = 40

    # header
    text(d, (pad, y), "TUNA DAY SHEET", F["h1"])
    text(d, (W - pad, y + 8), date, F["b"], SUB, anchor="ra")
    y += 58
    text(d, (pad, y), f"Marina Dbayeh  -  {home['lat']:.3f}, {home['lon']:.3f}", F["m"], SUB)
    y += 56

    # verdict banner
    v = rep["verdict"]
    vc = VCOL.get(v, (40, 60, 90))
    rrect(d, (pad, y, W - pad, y + 150), 22, vc)
    text(d, (pad + 30, y + 30), v, F["big"])
    for i, ln in enumerate(wrap(d, rep["verdict_reason"], F["s"], W - 2 * pad - 320)):
        text(d, (pad + 320, y + 36 + i * 30), ln, F["s"], (235, 240, 245))
    y += 178

    # conditions grid
    rrect(d, (pad, y, W - pad, y + 250), 18, CARD)
    text(d, (pad + 24, y + 18), "CONDITIONS", F["h2"], SUB)
    cells = [
        ("Wind", f"{oc['wind_min_kmh']:.0f}-{oc['wind_max_kmh']:.0f} km/h"),
        ("Sea", f"{oc['wave_max_m']:.1f} m"),
        ("Water", f"{oc['sst_avg_c']:.1f} C"),
        ("Pressure", f"{oc['pressure_hpa']:.0f} ({oc['pressure_trend_3h']:+.1f})"),
        ("Current", f"~{oc['current_avg_kmh']:.1f} km/h"),
        ("Front", f"{oc['front_spread_c']:.1f} C break"),
        ("Moon", f"{_short_phase(mn['phase'])} {mn['illumination_pct']}%"),
        ("Cloud", f"{oc['cloud_pct']}%"),
    ]
    cw = (W - 2 * pad - 48) / 4
    for i, (k, val) in enumerate(cells):
        cx = pad + 24 + (i % 4) * cw
        cy = y + 66 + (i // 4) * 92
        text(d, (cx, cy), k.upper(), F["xs"], SUB)
        text(d, (cx, cy + 26), val, F["b"])
    y += 278

    # bite windows
    rrect(d, (pad, y, W - pad, y + 132), 18, CARD)
    text(d, (pad + 24, y + 18), "BEST BITE WINDOWS", F["h2"], SUB)
    pw = ", ".join(f"{a:02d}:00-{b:02d}:00" for a, b in rep["prime_windows"])
    text(d, (pad + 24, y + 58), f"Prime light: {pw}", F["m"])
    text(d, (pad + 24, y + 92), f"Solunar majors {' / '.join(mn['major_periods'])}  "
                                f"minors {' / '.join(mn['minor_periods'])}", F["s"], SUB)
    y += 160

    # where to go
    text(d, (pad, y), "WHERE TO GO  (within range, with GPS)", F["h2"], SUB)
    y += 44
    for s in pick:
        rh = 150
        rrect(d, (pad, y, W - pad, y + rh), 16, CARD)
        rc = RCOL.get(s["rating"], (120, 120, 120))
        d.ellipse((pad + 18, y + 22, pad + 46, y + 50), fill=rc)
        text(d, (pad + 60, y + 18), s["name"], F["b"])
        text(d, (pad + 60, y + 56), s["area"], F["s"], SUB)
        text(d, (W - pad - 24, y + 18), s["rating"], F["b"], rc, anchor="ra")
        text(d, (W - pad - 24, y + 56), f"score {s['score']:.2f}", F["s"], SUB, anchor="ra")
        # coordinates + nav line
        text(d, (pad + 60, y + 92), f"{s['lat']:.4f}, {s['lon']:.4f}", F["mono"], (120, 200, 255))
        rng = "" if s.get("in_range") else "  (out of range)"
        text(d, (pad + 60, y + 122), f"{s['distance_nm']:.1f} nm  {s['heading']}  "
                                     f"brg {s['bearing_deg']:.0f}  -  SST {s['sst_c']:.1f}C  "
                                     f"wind {s['wind_kmh']:.0f}{rng}", F["s"], SUB)
        y += rh + 12
    y += 8

    # mini map
    mh = 560
    text(d, (pad, y), "MAP", F["h2"], SUB)
    y += 40
    try:
        mp, to_px = static_map((home["lat"], home["lon"]), 0.42, (W - 2 * pad, mh))
        img.paste(mp, (pad, y))
        md = ImageDraw.Draw(img)
        # home
        hx, hy = to_px(home["lat"], home["lon"])
        md.rectangle((pad + hx - 8, y + hy - 8, pad + hx + 8, y + hy + 8), fill=(255, 255, 255))
        md.text((pad + hx + 12, y + hy - 10), "Dbayeh", font=F["xs"], fill=(255, 255, 255))
        for s in pick:
            px, py = to_px(s["lat"], s["lon"])
            if 0 <= px <= W - 2 * pad and 0 <= py <= mh:
                rc = RCOL.get(s["rating"], (200, 200, 200))
                md.ellipse((pad + px - 9, y + py - 9, pad + px + 9, y + py + 9), fill=rc,
                           outline=(10, 20, 30), width=2)
                md.text((pad + px + 12, y + py - 10), s["name"], font=F["xs"], fill=(235, 240, 245))
    except Exception as e:
        rrect(d, (pad, y, W - pad, y + mh), 16, CARD)
        text(d, (pad + 24, y + 24), f"(map unavailable: {e})", F["s"], SUB)
    y += mh + 24

    # scout + footer
    rrect(d, (pad, y, W - pad, y + 188), 16, (20, 30, 46))
    text(d, (pad + 24, y + 18), "SCOUT FOR FRENZIES", F["h2"], (120, 200, 255))
    note = ("Open the live map, switch to the NASA satellite layer and tap any spot for its GPS "
            "(+ a 10 m Sentinel-2 image). Free satellites CANNOT see a live tuna bust - too small "
            "and brief. Use them for blooms and colour edges, then run the coordinates above and "
            "find the white water by watching for diving birds.")
    for i, ln in enumerate(wrap(d, note, F["s"], W - 2 * pad - 48)):
        text(d, (pad + 24, y + 58 + i * 30), ln, F["s"], INK)
    y += 210
    text(d, (pad, y), f"Sources: Open-Meteo (live) + NOAA VIIRS chlorophyll + solunar.  "
                      f"As of {rep['as_of']} Beirut.", F["xs"], SUB)

    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    img.save(os.path.join(out_dir, f"day-{date}.png"))
    latest = os.path.join(out_dir, "day.png")
    img.save(latest)
    return latest


if __name__ == "__main__":
    print("Building day-sheet image ...")
    path = build(get_report())
    print("Saved:", path)
