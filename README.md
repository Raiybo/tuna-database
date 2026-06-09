# 🐟 Tuna — bluefin casting-spot finder for the Lebanese coast

A small, data-driven system that ranks **day-to-day spots for casting to Atlantic
bluefin tuna** (_Thunnus thynnus_) along the Lebanese coast. For each spot it pulls
**live sea-surface temperature and wave height**, applies a tuna-suitability model,
and tells you **where to go today** — with coordinates.

Two ways to use it:

| | What | Best for |
|---|---|---|
| 🗺️ **Map dashboard** | [`web/`](web/) — interactive Leaflet map, spots colour-coded by today's suitability | Visual, on the phone before you launch |
| ⌨️ **CLI report** | `tuna` — ranked text/JSON/Markdown report | Terminal, automation, the daily GitHub Action |

> **Heads-up:** these are **search zones over deeper water and current edges**, not
> guaranteed marks. Refine the coordinates and add your own waypoints from real catch
> logs. Bluefin tuna are a **regulated species** — check current Lebanese / ICCAT
> seasons, quotas and permits before targeting them, and release what you can't legally keep.

---

## How it ranks a spot

Each spot gets a `0–1` suitability score (→ **PRIME / GOOD / FAIR / POOR**) from three live factors:

| Factor | Weight | Logic |
|---|---:|---|
| **Sea-surface temperature** | 0.55 | Optimal **18–24 °C** for warm-season Eastern-Med bluefin feeding near the surface; tapers off outside that. |
| **Castability (wave height)** | 0.30 | Glassy (≤ 0.8 m) is ideal for poppers/stickbaits; > 2 m is unsafe/unfishable. |
| **Thermal edge (front)** | 0.15 | Bait and tuna stack on temperature breaks. Spots on the warm/cold edge of the day's regional spread score higher. |

All thresholds live in [`src/tuna/config.py`](src/tuna/config.py) and
[`web/app.js`](web/app.js) — tune them to your local knowledge.

The spot database lives in [`data/spots.json`](data/spots.json) — **edit this file** to
add, move, or annotate marks. It's the single source of truth for both the CLI and the map.

---

## Quick start

### CLI report (no install, stdlib only)

```bash
# from the repo root
PYTHONPATH=src python -m tuna            # ranked table for today
PYTHONPATH=src python -m tuna --top 5    # only the top 5
PYTHONPATH=src python -m tuna --json     # machine-readable
PYTHONPATH=src python -m tuna --markdown # Markdown
```

Or install it as a `tuna` command:

```bash
pip install -e .
tuna --top 5
```

### Map dashboard

The map fetches `data/spots.json`, so serve from the **repo root**:

```bash
python3 -m http.server 8000
# then open http://localhost:8000/web/
```

To publish: enable **GitHub Pages** (Settings → Pages → deploy from `main`, root) and
visit `/web/`.

### Tests

```bash
pip install -e ".[dev]"
pytest
```

---

## Daily automation

[`.github/workflows/daily-report.yml`](.github/workflows/daily-report.yml) runs every
morning (~06:00 Beirut), regenerates `docs/today.md` with the day's ranked spots, and
commits it. Enable Actions on the repo to turn it on (or trigger it manually from the
Actions tab).

---

## Project layout

```
data/spots.json          Spot database (coordinates, structure, notes) — edit this
src/tuna/
  config.py              Scoring thresholds & weights
  scoring.py             Pure scoring functions (SST, wave, thermal front)
  marine.py              Open-Meteo Marine API client (stdlib urllib)
  spots.py               Load & validate spots
  report.py              Fetch live data + rank spots
  cli.py                 `tuna` command (table / JSON / Markdown)
web/                     Leaflet map dashboard (live, client-side)
tests/                   pytest unit tests for the scoring model
```

Data: live marine conditions from [Open-Meteo](https://open-meteo.com/) (free, no API key).
License: MIT.
