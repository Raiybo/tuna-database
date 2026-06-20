"""Load and validate the data files: spots, home port, and sightings."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SPOTS_FILE = DATA_DIR / "spots.json"
HOME_FILE = DATA_DIR / "home.json"
SIGHTINGS_FILE = DATA_DIR / "sightings.json"
CATCHES_FILE = DATA_DIR / "catches.json"


@dataclass
class Spot:
    id: str
    name: str
    area: str
    lat: float
    lon: float
    depth_zone: str
    structure: str
    best_months: list
    notes: str


@dataclass
class Home:
    name: str
    lat: float
    lon: float
    max_range_km: float
    note: str = ""


def load_spots(path: Path | None = None) -> list[Spot]:
    path = Path(path) if path else SPOTS_FILE
    raw = json.loads(path.read_text(encoding="utf-8"))
    spots: list[Spot] = []
    seen: set[str] = set()
    for s in raw.get("spots", []):
        sid = s["id"]
        if sid in seen:
            raise ValueError(f"Duplicate spot id: {sid}")
        seen.add(sid)
        lat, lon = float(s["lat"]), float(s["lon"])
        if not (33.0 <= lat <= 34.8 and 34.8 <= lon <= 36.1):
            raise ValueError(f"Spot {sid} lat/lon out of Lebanon range: {lat}, {lon}")
        spots.append(Spot(
            id=sid, name=s["name"], area=s["area"], lat=lat, lon=lon,
            depth_zone=s.get("depth_zone", ""), structure=s.get("structure", ""),
            best_months=list(s.get("best_months", [])), notes=s.get("notes", ""),
        ))
    if not spots:
        raise ValueError(f"No spots found in {path}")
    return spots


def load_home(path: Path | None = None) -> Home:
    path = Path(path) if path else HOME_FILE
    d = json.loads(path.read_text(encoding="utf-8"))
    return Home(
        name=d.get("name", "Home"),
        lat=float(d["lat"]),
        lon=float(d["lon"]),
        max_range_km=float(d.get("max_range_km", 40)),
        note=d.get("note", ""),
    )


def load_sightings(path: Path | None = None) -> list[dict]:
    """Return real sightings with a parsed UTC datetime in ``_dt``.

    Rows flagged ``"example": true`` are skipped. Missing file -> empty list.
    """
    path = Path(path) if path else SIGHTINGS_FILE
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    for s in raw.get("sightings", []):
        if s.get("example"):
            continue
        try:
            dt = datetime.strptime(s["date"], "%Y-%m-%d").replace(
                hour=12, tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        out.append({**s, "_dt": dt})
    return out


def load_catches(path: Path | None = None) -> list[dict]:
    """Return logged catches with a parsed UTC datetime in ``_dt``.

    Each row records the conditions you caught (or blanked) under so the pattern
    layer can learn what actually works locally. Rows flagged ``"example": true``
    are skipped. Schema is documented in data/catches.json. Missing file -> [].
    """
    path = Path(path) if path else CATCHES_FILE
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict] = []
    for c in raw.get("catches", []):
        if c.get("example"):
            continue
        try:
            dt = datetime.strptime(c["date"], "%Y-%m-%d").replace(
                hour=12, tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        out.append({**c, "_dt": dt})
    return out
