"""Load and validate the spot database (data/spots.json)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "spots.json"


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


def load_spots(path: Path | None = None) -> list[Spot]:
    """Read, validate and return all spots. Raises on malformed data."""
    path = Path(path) if path else DATA_FILE
    raw = json.loads(path.read_text(encoding="utf-8"))
    spots: list[Spot] = []
    seen: set[str] = set()
    for s in raw.get("spots", []):
        sid = s["id"]
        if sid in seen:
            raise ValueError(f"Duplicate spot id: {sid}")
        seen.add(sid)
        lat, lon = float(s["lat"]), float(s["lon"])
        # Sanity box around Lebanese waters.
        if not (33.0 <= lat <= 34.8 and 34.8 <= lon <= 36.1):
            raise ValueError(f"Spot {sid} lat/lon out of Lebanon range: {lat}, {lon}")
        spots.append(
            Spot(
                id=sid,
                name=s["name"],
                area=s["area"],
                lat=lat,
                lon=lon,
                depth_zone=s.get("depth_zone", ""),
                structure=s.get("structure", ""),
                best_months=list(s.get("best_months", [])),
                notes=s.get("notes", ""),
            )
        )
    if not spots:
        raise ValueError(f"No spots found in {path}")
    return spots
