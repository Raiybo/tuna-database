"""Learn from your logbook: validate the model and surface what actually works.

Reads data/catches.json (catches AND blanks). With enough trips it reports your
hit-rate and the conditions that separate catches from blanks - turning the
heuristic model into something calibrated to YOUR water. Dormant (honest 'log
some trips') until you have data.
"""
from __future__ import annotations

import json
from datetime import date
from statistics import mean

from .spots import CATCHES_FILE, load_catches

_DIMS = [("sst_c", "SST °C"), ("wind_kmh", "wind km/h"),
         ("pressure_trend", "pressure 3h"), ("hour", "hour")]


def append_catch(record: dict, path=None) -> None:
    """Append one trip to data/catches.json (creating the structure if needed)."""
    path = path or CATCHES_FILE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {"catches": []}
    raw.setdefault("catches", []).append(record)
    path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")


def _is_catch(c):
    return c.get("result") == "catch" or (c.get("n") or 0) > 0


def summary() -> str:
    catches = load_catches()
    if not catches:
        return ("No trips logged yet. Record results with:\n"
                "  tuna log --catch 2 --spot beirut-canyon --hour 6   (a 2-fish day)\n"
                "  tuna log --blank --spot tabarja --hour 7           (a blank)\n"
                "Log catches AND blanks - the contrast is what the model learns from.")

    wins = [c for c in catches if _is_catch(c)]
    blanks = [c for c in catches if not _is_catch(c)]
    rate = 100.0 * len(wins) / len(catches)
    L = [f"Logbook: {len(catches)} trips · {len(wins)} catches · {len(blanks)} blanks "
         f"· hit-rate {rate:.0f}%"]

    if wins and blanks:
        L.append("\nWhat separates your catches from your blanks:")
        for key, lbl in _DIMS:
            cw = [c[key] for c in wins if c.get(key) is not None]
            cb = [c[key] for c in blanks if c.get(key) is not None]
            if cw and cb:
                L.append(f"  {lbl:14} catches avg {mean(cw):.1f}  vs  blanks avg {mean(cb):.1f}")
        spots = {}
        for c in wins:
            sid = c.get("spot_id")
            if sid:
                spots[sid] = spots.get(sid, 0) + 1
        if spots:
            top = sorted(spots.items(), key=lambda x: x[1], reverse=True)[:3]
            L.append("  best spots:   " + ", ".join(f"{s} ({n})" for s, n in top))
    elif not blanks:
        L.append("Log some blanks too - without them the model can't tell what's "
                 "different about a good day.")

    if len(catches) < 12:
        L.append(f"\n{12 - len(catches)} more logged trips and the pattern engine starts "
                 "auto-flagging days that match your hook-ups.")
    return "\n".join(L)


def new_record(result, n=0, spot_id=None, lat=None, lon=None, hour=None,
               species=None, sst_c=None, wind_kmh=None, pressure_trend=None,
               moon=None, note=None, day=None) -> dict:
    rec = {"date": day or date.today().isoformat(), "result": result, "n": n}
    for k, v in (("species", species), ("spot_id", spot_id), ("lat", lat), ("lon", lon),
                 ("hour", hour), ("sst_c", sst_c), ("wind_kmh", wind_kmh),
                 ("pressure_trend", pressure_trend), ("moon", moon), ("note", note)):
        if v is not None:
            rec[k] = v
    return rec
