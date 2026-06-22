"""Fishing-fleet activity from AIS via Global Fishing Watch (DORMANT until a token).

Where the commercial fleet works is real, observed evidence of fish. GFW offers a
FREE API token (register at globalfishingwatch.org/our-apis). This module is the
ready-to-activate hook: with GFW_TOKEN set it returns recent apparent-fishing
effort near the marina; without it, it returns disabled and the rest of the
system is unaffected.

Set env GFW_TOKEN to enable. Effort is queried from the 4wings report API over a
small bbox for the last ~14 days.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from ._http import post


def enabled() -> bool:
    return bool(os.environ.get("GFW_TOKEN"))


def fetch_effort(lat: float, lon: float, half_deg: float = 0.25, days: int = 14) -> dict:
    """Return {'enabled': bool, 'cells': [...], 'note': str}. Never raises."""
    token = os.environ.get("GFW_TOKEN")
    if not token:
        return {"enabled": False, "cells": [],
                "note": "GFW_TOKEN not set - fleet-activity layer dormant"}
    try:
        end = _dt.date.today()
        start = end - _dt.timedelta(days=days)
        geojson = {"type": "Polygon", "coordinates": [[
            [lon - half_deg, lat - half_deg], [lon + half_deg, lat - half_deg],
            [lon + half_deg, lat + half_deg], [lon - half_deg, lat + half_deg],
            [lon - half_deg, lat - half_deg]]]}
        url = ("https://gateway.api.globalfishingwatch.org/v3/4wings/report"
               "?spatial-resolution=HIGH&temporal-resolution=ENTIRE"
               "&datasets[0]=public-global-fishing-effort:latest&format=JSON"
               f"&date-range={start.isoformat()},{end.isoformat()}")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        status, body = post(url, json.dumps({"geojson": geojson}).encode(), headers, timeout=40)
        data = json.loads(body) if body else {}
        rows = (data.get("entries") or [{}])[0].get("public-global-fishing-effort", [])
        cells = sorted(
            ({"lat": r.get("lat"), "lon": r.get("lon"), "hours": r.get("hours", 0)}
             for r in rows if r.get("hours")),
            key=lambda c: c["hours"], reverse=True)[:12]
        return {"enabled": True, "cells": cells,
                "note": f"GFW apparent fishing effort, last {days} days ({len(cells)} hot cells)"}
    except Exception as e:
        return {"enabled": True, "cells": [], "note": f"GFW query failed: {e.__class__.__name__}"}
