"""tuna - daily bluefin day-sheet for your marina on the Lebanese coast.

Usage:
    tuna                 # today's ocean sheet + where to go (from your marina)
    tuna --all           # include spots beyond your day range
    tuna --top 5         # cap the spot list
    tuna --range 60      # override day-trip radius (km)
    tuna --home 34.0,35.6  # override home port (lat,lon) just for this run
    tuna --chl           # try the (gated) chlorophyll bait source this run
    tuna --json | --markdown
"""
from __future__ import annotations

import argparse
import json

from . import __version__, config
from . import report as report_mod
from .conditions import compass
from .spots import Home


def _n(v, suffix="", nd=1):
    return f"{v:.{nd}f}{suffix}" if v is not None else "n/a"


def _trend_word(t):
    if t is None:
        return "n/a"
    if t > 0.5:
        return f"rising (+{t:.1f}/3h)"
    if t < -0.5:
        return f"falling ({t:.1f}/3h)"
    return f"steady ({t:+.1f}/3h)"


def _windows() -> str:
    return " and ".join(f"{a:02d}:00-{b:02d}:00" for a, b in config.PRIME_WINDOWS)


def _bait_line(o) -> str:
    if o.front_spread is None:
        front = "thermal break: n/a"
    elif o.front_spread < config.FRONT_MIN_SPREAD:
        front = f"thermal break: weak (uniform, {o.front_spread} C spread)"
    else:
        front = f"thermal break: ACTIVE ({o.front_spread} C spread - work the seams)"
    cur = "current edges: n/a" if o.current_avg is None else (
        f"current edges: {'moderate' if o.current_avg >= 0.3 else 'slack'} (~{o.current_avg} km/h)")
    if not o.chl_enabled:
        chl = "chlorophyll feed: disabled (no fresh free source) - add one to activate"
    else:
        chl = "chlorophyll feed: enabled"
    sights = "sightings logged: yes" if o.has_sightings else "no recent sightings logged"
    return f"   {front}\n   {cur}\n   {chl} - {sights}"


def render_sheet(rep) -> str:
    o = rep.ocean
    L = []
    bar = "=" * 64
    L.append(bar)
    L.append(" TUNA - bluefin day sheet - Lebanese coast")
    L.append(f" From: {rep.home.name}  {rep.home.lat:.3f}, {rep.home.lon:.3f}"
             f"  (range {rep.home.max_range_km:.0f} km)")
    L.append(f" As of {o.date_label} (Asia/Beirut)")
    L.append(bar)
    L.append("")
    L.append(f" VERDICT:  {o.verdict}  -  {o.verdict_reason}")
    L.append("")
    L.append(" OCEAN TODAY")
    L.append(f"   Sea temp    {_n(o.sst_min,' C')}-{_n(o.sst_max,' C')} (avg {_n(o.sst_avg)})")
    L.append(f"   Swell       {_n(o.wave_min,' m')}-{_n(o.wave_max,' m')}")
    L.append(f"   Wind        {_n(o.wind_min,' km/h')}-{_n(o.wind_max,' km/h')} "
             f"{compass(o.wind_dir)} (gusts ~{_n(o.gust_max)})")
    L.append(f"   Pressure    {_n(o.pressure,' hPa')}, {_trend_word(o.pressure_trend)}")
    L.append(f"   Current     ~{_n(o.current_avg,' km/h')}")
    L.append(f"   Sky         {_n(o.cloud,'%',0)} cloud")
    L.append(f"   Moon        {o.moon['phase']}, {o.moon['illumination_pct']}% lit")
    L.append(f"   Solunar     majors {' / '.join(o.moon['major_periods'])}  "
             f"minors {' / '.join(o.moon['minor_periods'])}  (approx)")
    L.append(f"   Prime light {_windows()}")
    L.append("")
    L.append(" BAIT / FORAGE READ")
    L.append(_bait_line(o))
    L.append("")
    return "\n".join(L)


def render_spots(rep, show_all: bool, top: int) -> str:
    shown = rep.spots if show_all else [r for r in rep.spots if r.cond.in_range]
    if not shown:  # nothing in range -> show everything rather than an empty sheet
        shown = rep.spots
        note = " (none within range - showing all; widen --range or move home port)"
    else:
        note = "" if show_all else f" (within {rep.home.max_range_km:.0f} km of your marina)"
    if top > 0:
        shown = shown[:top]

    L = [f" WHERE TO GO{note}",
         f"  {'#':>2}  {'RATING':6}  {'SCORE':>5}  {'DIST':>7}  {'HEAD':5}  "
         f"{'SST':>6}  {'WIND':>8}  SPOT",
         "  " + "-" * 74]
    for i, r in enumerate(shown, 1):
        m, w = r.cond.marine, r.cond.weather
        head = f"{compass(r.cond.bearing_deg)}"
        L.append(
            f"  {i:>2}  {r.score.rating:6}  {r.score.total:>5.2f}  "
            f"{r.cond.dist_nm:>4.1f}nm  {head:5}  {_n(m.get('sst'),'C'):>6}  "
            f"{_n(w.get('wind_kmh'),''):>4} {compass(w.get('wind_dir')):>3}  "
            f"{r.spot.name} ({r.spot.area})")

    if not show_all:
        out = [r for r in rep.spots if not r.cond.in_range]
        if out:
            tail = ", ".join(f"{r.spot.name} {r.cond.dist_nm:.0f}nm" for r in out[:5])
            L.append(f"  out of range (--all to show): {tail}")
    return "\n".join(L)


def render_bestbet(rep) -> str:
    b = rep.ocean.best_in_range
    if not b:
        return ""
    return ("\n BEST BET -> "
            f"{b.spot.name} ({b.spot.area})\n"
            f"   {b.cond.dist_nm:.1f} nm, bearing {b.cond.bearing_deg:.0f} "
            f"({compass(b.cond.bearing_deg)}) from your marina  |  "
            f"SST {_n(b.cond.marine.get('sst'),' C')}, "
            f"score {b.score.total:.2f} ({b.score.rating})\n"
            f"   {b.spot.notes}\n"
            "   Reminder: bluefin are regulated - verify season/quota/permit before keeping fish.")


def render_footer() -> str:
    return ("\n Sources: Open-Meteo Marine + Weather (live) - solunar/moon computed."
            " Bait read from thermal fronts + currents (+ chlorophyll when enabled)"
            " + your sightings log. Spots are search zones, not guaranteed marks.")


def to_dict(rep) -> dict:
    o = rep.ocean
    return {
        "as_of": o.date_label,
        "home": {"name": rep.home.name, "lat": rep.home.lat, "lon": rep.home.lon,
                 "range_km": rep.home.max_range_km},
        "verdict": o.verdict,
        "verdict_reason": o.verdict_reason,
        "ocean": {
            "sst_avg_c": o.sst_avg, "sst_min_c": o.sst_min, "sst_max_c": o.sst_max,
            "wave_min_m": o.wave_min, "wave_max_m": o.wave_max,
            "wind_min_kmh": o.wind_min, "wind_max_kmh": o.wind_max,
            "wind_dir": o.wind_dir, "gust_max_kmh": o.gust_max,
            "pressure_hpa": o.pressure, "pressure_trend_3h": o.pressure_trend,
            "current_avg_kmh": o.current_avg, "cloud_pct": o.cloud,
            "front_spread_c": o.front_spread,
        },
        "moon": o.moon,
        "prime_windows": [list(w) for w in config.PRIME_WINDOWS],
        "spots": [
            {
                "rank": i, "id": r.spot.id, "name": r.spot.name, "area": r.spot.area,
                "lat": r.spot.lat, "lon": r.spot.lon,
                "distance_nm": round(r.cond.dist_nm, 1),
                "distance_km": r.cond.dist_km,
                "bearing_deg": r.cond.bearing_deg, "heading": compass(r.cond.bearing_deg),
                "in_range": r.cond.in_range,
                "rating": r.score.rating, "score": r.score.total,
                "factors": r.score.contrib, "sighting_boost": r.score.boost,
                "sst_c": r.cond.marine.get("sst"), "wave_m": r.cond.marine.get("wave"),
                "wind_kmh": r.cond.weather.get("wind_kmh"),
                "current_kmh": r.cond.marine.get("current_kmh"),
                "notes": r.spot.notes,
            }
            for i, r in enumerate(rep.spots, 1)
        ],
    }


def render_markdown(rep) -> str:
    o = rep.ocean
    L = [f"# Tuna day sheet - {o.date_label} (Asia/Beirut)",
         "",
         f"**From {rep.home.name}** ({rep.home.lat:.3f}, {rep.home.lon:.3f}, "
         f"range {rep.home.max_range_km:.0f} km)",
         "",
         f"## VERDICT: {o.verdict} - {o.verdict_reason}",
         "",
         "| Ocean | |",
         "|---|---|",
         f"| Sea temp | {_n(o.sst_min,' C')}-{_n(o.sst_max,' C')} (avg {_n(o.sst_avg)}) |",
         f"| Swell | {_n(o.wave_min,' m')}-{_n(o.wave_max,' m')} |",
         f"| Wind | {_n(o.wind_min,' km/h')}-{_n(o.wind_max,' km/h')} {compass(o.wind_dir)} |",
         f"| Pressure | {_n(o.pressure,' hPa')}, {_trend_word(o.pressure_trend)} |",
         f"| Current | ~{_n(o.current_avg,' km/h')} |",
         f"| Moon | {o.moon['phase']}, {o.moon['illumination_pct']}% |",
         f"| Solunar majors | {' / '.join(o.moon['major_periods'])} (approx) |",
         "",
         "## Where to go (within range, best first)",
         "",
         "| # | Rating | Score | Dist | Head | SST | Wind | Spot | Coordinates |",
         "|--:|:--|--:|--:|:--|--:|--:|:--|:--|"]
    shown = [r for r in rep.spots if r.cond.in_range] or rep.spots
    for i, r in enumerate(shown, 1):
        m, w = r.cond.marine, r.cond.weather
        L.append(
            f"| {i} | {r.score.rating} | {r.score.total:.2f} | "
            f"{r.cond.dist_nm:.1f} nm | {compass(r.cond.bearing_deg)} | "
            f"{_n(m.get('sst'),' C')} | {_n(w.get('wind_kmh'),' km/h')} | "
            f"{r.spot.name} ({r.spot.area}) | {r.spot.lat:.3f}, {r.spot.lon:.3f} |")
    b = o.best_in_range
    if b:
        L += ["",
              f"**Best bet:** {b.spot.name} - {b.cond.dist_nm:.1f} nm bearing "
              f"{b.cond.bearing_deg:.0f} ({compass(b.cond.bearing_deg)}). {b.spot.notes}",
              "",
              "> Search zones, not guaranteed marks. Bluefin are regulated - check "
              "Lebanese / ICCAT season, quota and permits before targeting them."]
    return "\n".join(L)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tuna", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--all", action="store_true", help="include spots beyond day range")
    p.add_argument("--top", type=int, default=0, metavar="N", help="cap the spot list")
    p.add_argument("--range", type=float, default=None, metavar="KM",
                   help="override day-trip radius")
    p.add_argument("--home", default=None, metavar="LAT,LON",
                   help="override home port for this run")
    p.add_argument("--chl", action="store_true", help="try the chlorophyll bait source")
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.add_argument("--markdown", action="store_true", help="emit Markdown")
    p.add_argument("--version", action="version", version=f"tuna {__version__}")
    args = p.parse_args(argv)

    home_override = None
    if args.home or args.range is not None:
        from .spots import load_home
        base = load_home()
        lat, lon = base.lat, base.lon
        if args.home:
            lat, lon = (float(x) for x in args.home.split(","))
        home_override = Home(name=base.name if not args.home else "Custom home",
                             lat=lat, lon=lon,
                             max_range_km=args.range if args.range is not None
                             else base.max_range_km, note=base.note)

    rep = report_mod.build_report(enable_chl=True if args.chl else None,
                                  home_override=home_override)

    if args.json:
        print(json.dumps(to_dict(rep), indent=2))
    elif args.markdown:
        print(render_markdown(rep))
    else:
        print(render_sheet(rep))
        print(render_spots(rep, args.all, args.top))
        print(render_bestbet(rep))
        print(render_footer())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
