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

# Forecast — which day is good, and the peak bite window
PYTHONPATH=src python3 -m tuna --forecast        # next 5 days, peak windows, patterns
PYTHONPATH=src python3 -m tuna --hours           # today's hourly bite curve
PYTHONPATH=src python3 -m tuna --forecast --days 7

# Map dashboard — serve from the repo root so it can read data/*.json
python3 -m http.server 8000                 # open http://localhost:8000/web/

# Tests
pip install -e ".[dev]" && pytest
```

## Forecast, peak time & pattern recognition

`tuna --forecast` pulls **hourly** marine + weather over the next several days (two batched
requests) and scores **every daylight hour** with a time-of-day **feeding** factor — prime light
windows (dawn/dusk) stacked with **solunar** majors/minors. For each day it picks the best
*reachable* spot, the **peak bite window**, a verdict, and the **patterns** that line up:

- **Thermal break active** — bait stacks on the SST seam
- **Pre-frontal feed** — pressure easing before a change
- **Solunar stack at light** — a moon major landing on dawn/dusk
- **Productive water** — chlorophyll in the forage band
- **Calm casting window** — low wind & swell at the peak
- **Strong moon** — new/full peak energy

**It learns from you.** Log trips in [`data/catches.json`](data/catches.json) (catches *and* blanks);
when a day's conditions resemble your past hook-ups, a **"Matches your past catches"** pattern fires.
Dormant until you have data — it never invents confidence it hasn't earned.

## Phone notifications (the night before)

[`tools/notify.py`](tools/notify.py) composes tomorrow's verdict + peak window and pushes it to your
phone. Default channel is **[ntfy.sh](https://ntfy.sh)** (no account):

1. Install the **ntfy** app, subscribe to a private topic name (e.g. `tuna-<something-random>`).
2. Add repo secret **`NTFY_TOPIC`** (Settings → Secrets → Actions). Optional: `NTFY_SERVER`,
   `NTFY_TOKEN` if you protect the topic. Telegram (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`) and
   Pushover (`PUSHOVER_TOKEN`/`PUSHOVER_USER`) also work if set.
3. [`.github/workflows/forecast-notify.yml`](.github/workflows/forecast-notify.yml) sends it each
   evening (~18:00 Beirut). Test anytime from the Actions tab, or locally:

```bash
NTFY_TOPIC=your-topic PYTHONPATH=src python tools/notify.py --day tomorrow
PYTHONPATH=src python tools/notify.py --dry-run    # compose without sending
```

## Daily automation

[`.github/workflows/daily-report.yml`](.github/workflows/daily-report.yml) regenerates
`docs/today.md` + day image every morning (~06:00 Beirut); the evening workflow pushes the
forecast. Enable Actions to turn them on. (Pushing workflow files needs the `workflow` token scope.)

## Project layout

```
data/    home.json · spots.json · sightings.json · catches.json   ← edit these
src/tuna/
  config.py        scoring thresholds, factor weights, hourly weights
  scoring.py       pure factor scores, weighted blend, feeding-time score
  sources/         openmeteo_marine · openmeteo_weather · chlorophyll · solunar
  conditions.py    parallel multi-source gather + distance/bearing from home
  model.py         Conditions -> suitability score
  ocean.py         daily ocean summary + go/no-go verdict
  forecast.py      multi-day hourly forecast + peak bite window
  patterns.py      pattern recognition + learning from your catch log
  report.py        orchestrate · cli.py  the `tuna` command
tools/   hotspots.py · day_image.py · notify.py (phone push)
web/     interactive map dashboard (live, client-side)
tests/   pytest unit tests
```

Data: [Open-Meteo](https://open-meteo.com/) (free, no key). License: MIT.
