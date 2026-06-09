# 🐟 Tuna — bluefin day-sheet for your marina (Lebanese coast)

Ask it day to day: **"How's the ocean, and is it a good day to chase bluefin?"**
For your home port it pulls **multiple live data sources**, reads the water for bait/forage
signals, and tells you **GO / DECENT / MARGINAL / TOUGH** plus **where to run** — ranked by
distance from your marina and today's conditions, with coordinates and headings. Plus an
**interactive map** centered on you, spots colour-coded by today's score, with a sightings layer.

| | What | Best for |
|---|---|---|
| 🗺️ **Map dashboard** | [`web/`](web/) — Leaflet map from your marina, range ring, live conditions, sightings layer | Visual planning on the phone |
| ⌨️ **Day sheet (CLI)** | `tuna` — ocean summary + go/no-go + ranked spots | Terminal, automation, the daily Action |

> These are **search zones over deeper water / current edges**, not guaranteed marks. Bluefin tuna
> are a **regulated species** — check current Lebanese / ICCAT seasons, quotas and permits before
> targeting them, and release what you can't legally keep.

---

## It's measured from *your* marina

[`data/home.json`](data/home.json) sets your home port and day-trip radius:

```json
{ "name": "Marina Baye", "lat": 33.935, "lon": 35.59, "max_range_km": 40 }
```

Every spot gets a **distance (nm)** and **heading** from there; spots beyond `max_range_km` are
flagged out-of-range. The map centers on you with a dashed range ring. Override per run with
`tuna --home 34.0,35.6 --range 60`.

## Multiple live sources → one score

Each spot's `0–1` suitability (→ **PRIME / GOOD / FAIR / POOR**) blends independent live factors.
If a source is missing, its weight is **renormalised** over the rest, so the score degrades cleanly.

| Factor | Source | Weight | Read |
|---|---|--:|---|
| Sea-surface temp | Open-Meteo Marine | 0.22 | Optimal 18–24 °C warm-season feeding |
| Thermal front | derived from the SST field | 0.13 | Breaks concentrate bait |
| Bait / chlorophyll | ERDDAP (gated) | 0.15 | Productivity proxy — *off until a fresh feed is wired* |
| Ocean current | Open-Meteo Marine | 0.10 | A moderate drift makes feeding edges |
| Castability | wind + wave | 0.17 | Can you cast & spot busts? |
| Pressure trend | Open-Meteo Weather | 0.10 | A slow fall often turns fish on |
| Solunar / moon | computed locally | 0.13 | Major/minor periods, new/full strength |

Recent **sightings** you log ([`data/sightings.json`](data/sightings.json)) add an extra boost to
nearby spots and appear on the map. Tunables live in [`src/tuna/config.py`](src/tuna/config.py)
(and mirrored in [`web/app.js`](web/app.js)).

### A note on "bait in the water"

The free satellite chlorophyll feeds reachable without a login are currently frozen (~2022), so
chlorophyll is **disabled by default** (`CHL_ENABLED = False`). Today's *live* bait read comes from
**thermal fronts + current edges + your sightings log**. To fortify: add a fresh source to
[`src/tuna/sources/chlorophyll.py`](src/tuna/sources/chlorophyll.py) and flip `CHL_ENABLED` on — the
weight activates automatically. This is the natural seam for merging your other repo.

---

## Quick start

```bash
# Day sheet (stdlib only, no install)
PYTHONPATH=src python3 -m tuna              # today's ocean + where to go
PYTHONPATH=src python3 -m tuna --all        # include spots beyond day range
PYTHONPATH=src python3 -m tuna --json       # machine-readable
PYTHONPATH=src python3 -m tuna --markdown   # Markdown (daily Action)

# Map dashboard — serve from the repo root so it can read data/*.json
python3 -m http.server 8000                 # open http://localhost:8000/web/

# Tests
pip install -e ".[dev]" && pytest
```

## Daily automation

[`.github/workflows/daily-report.yml`](.github/workflows/daily-report.yml) regenerates
`docs/today.md` every morning (~06:00 Beirut). Enable Actions to turn it on. (Pushing this file
needs the `workflow` token scope — see commit notes.)

## Project layout

```
data/    home.json · spots.json · sightings.json        ← edit these
src/tuna/
  config.py        scoring thresholds & factor weights
  scoring.py       pure factor scores + weighted blend
  sources/         openmeteo_marine · openmeteo_weather · chlorophyll · solunar
  conditions.py    parallel multi-source gather + distance/bearing from home
  model.py         Conditions -> suitability score
  ocean.py         daily ocean summary + go/no-go verdict
  report.py        orchestrate · cli.py  the `tuna` command
web/     interactive map dashboard (live, client-side)
tests/   pytest unit tests
```

Data: [Open-Meteo](https://open-meteo.com/) (free, no key). License: MIT.
