"""tuna - daily bluefin casting-spot finder for the Lebanese coast.

Usage:
    tuna                 # ranked table for today
    tuna --top 5         # only the top 5 spots
    tuna --json          # machine-readable JSON
    tuna --markdown      # Markdown (used by the daily GitHub Action)
"""
from __future__ import annotations

import argparse
import json

from . import __version__, config
from . import report as report_mod


def _num(v, suffix="", nd=1):
    return f"{v:.{nd}f}{suffix}" if v is not None else "n/a"


def _windows() -> str:
    parts = [f"{a:02d}:00-{b:02d}:00" for a, b in config.PRIME_WINDOWS]
    return " and ".join(parts)


def render_table(reports) -> str:
    rows = [
        f"{'#':>2}  {'RATING':6}  {'SCORE':>5}  {'SST':>7}  {'WAVE':>6}  {'SPOT':22}  AREA",
        "-" * 78,
    ]
    for i, r in enumerate(reports, 1):
        rows.append(
            f"{i:>2}  {r.rating:6}  {r.suit.total:>5.2f}  "
            f"{_num(r.marine.sst_now, ' C'):>7}  {_num(r.marine.wave_now, ' m'):>6}  "
            f"{r.spot.name[:22]:22}  {r.spot.area}"
        )
    return "\n".join(rows)


def render_markdown(reports) -> str:
    asof = reports[0].marine.hour_label if reports else "n/a"
    out = [
        "# Today's bluefin casting spots - Lebanese coast",
        "",
        f"_As of {asof} (Asia/Beirut). Prime surface windows: {_windows()}._",
        "",
        "| # | Rating | Score | SST | Wave | Spot | Area | Coordinates |",
        "|--:|:------|------:|----:|-----:|:-----|:-----|:------------|",
    ]
    for i, r in enumerate(reports, 1):
        out.append(
            f"| {i} | {r.rating} | {r.suit.total:.2f} | "
            f"{_num(r.marine.sst_now, ' C')} | {_num(r.marine.wave_now, ' m')} | "
            f"{r.spot.name} | {r.spot.area} | "
            f"{r.spot.lat:.3f}, {r.spot.lon:.3f} |"
        )
    if reports:
        top = reports[0]
        out += [
            "",
            f"**Best bet:** {top.spot.name} ({top.spot.area}) - "
            f"{top.spot.lat:.3f}, {top.spot.lon:.3f}. {top.spot.notes}",
            "",
            "> Search zones, not guaranteed marks. Bluefin tuna are a regulated "
            "species - check current Lebanese / ICCAT seasons, quotas and permits "
            "before targeting them, and release fish you cannot legally keep.",
        ]
    return "\n".join(out)


def _to_dict(reports) -> dict:
    return {
        "as_of": reports[0].marine.hour_label if reports else None,
        "prime_windows": [list(w) for w in config.PRIME_WINDOWS],
        "spots": [
            {
                "rank": i,
                "id": r.spot.id,
                "name": r.spot.name,
                "area": r.spot.area,
                "lat": r.spot.lat,
                "lon": r.spot.lon,
                "rating": r.rating,
                "score": r.suit.total,
                "sst_c": r.marine.sst_now,
                "wave_m": r.marine.wave_now,
                "sst_min_c": r.marine.sst_min,
                "sst_max_c": r.marine.sst_max,
                "factors": {
                    "sst": r.suit.sst,
                    "wave": r.suit.wave,
                    "front": round(r.suit.front, 3),
                },
                "notes": r.spot.notes,
            }
            for i, r in enumerate(reports, 1)
        ],
    }


def _banner(reports) -> str:
    asof = reports[0].marine.hour_label if reports else "n/a"
    return (
        "TUNA - bluefin casting spots, Lebanese coast\n"
        f"As of {asof} (Asia/Beirut)  |  prime surface windows: {_windows()}"
    )


def _guidance(reports) -> str:
    if not reports:
        return "No spots to report."
    t = reports[0]
    return (
        f"Best bet -> {t.spot.name} ({t.spot.area}) at {t.spot.lat:.3f}, "
        f"{t.spot.lon:.3f}\n  {t.spot.notes}\n"
        "  Reminder: bluefin are regulated - verify season/quota/permit before keeping fish."
    )


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tuna", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", action="store_true", help="emit JSON")
    p.add_argument("--markdown", action="store_true", help="emit Markdown")
    p.add_argument("--top", type=int, default=0, metavar="N", help="only show the top N spots")
    p.add_argument("--version", action="version", version=f"tuna {__version__}")
    args = p.parse_args(argv)

    reports = report_mod.build_report()
    if args.top > 0:
        reports = reports[: args.top]

    if args.json:
        print(json.dumps(_to_dict(reports), indent=2))
    elif args.markdown:
        print(render_markdown(reports))
    else:
        print(_banner(reports))
        print()
        print(render_table(reports))
        print()
        print(_guidance(reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
