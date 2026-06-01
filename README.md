# 🎣 Tuna — Daily fishing forecast for Marina Dbaye

Tells you **if it's a good day**, **when the fish are likely feeding**, and **where to fish** — for bluefin / skipjack / bonito, jigging & casting within ~5 nm of Dbaye.

## Daily use

```powershell
python tuna.py
```

Fetches live data, writes **`report.html`**, and prints a summary. Open `report.html` on your phone before you leave the dock.

## After a trip — log it (one line)

```powershell
python tuna.py log bonito 3            # caught 3 bonito
python tuna.py log skipjack 2 birds off the point   # + a note
python tuna.py log blank               # went out, nothing
```

The log auto-stamps that day's conditions (score, SST break, chlorophyll, moon, wind, spot).
After ~3 productive trips, the report starts telling you **how today matches your good days**
and what conditions actually catch fish for *you*.

## Make it yours

Edit **`spots.json`** — replace the placeholder marks with your **real GPS spots**
(drop-offs, reefs, wrecks). The "where" gets much sharper when it ranks *your* grounds.

## Where the data comes from

| Signal | Source | Notes |
|---|---|---|
| Wind, pressure, sun | Open-Meteo Weather | live forecast |
| Currents, waves | Open-Meteo Marine | live forecast |
| Sea-surface temp (5 km, breaks) | NOAA CoralTemp (ERDDAP) | observed, ~1-day old, gap-free |
| Chlorophyll / bait edges (~4 km) | NOAA VIIRS (ERDDAP) | observed, cloud-gappy |
| Bite timing (solunar) | `ephem` moon math | calculated, offline |

> ⚠️ No system sees the actual fish. This points you to the best **conditions** —
> the break, the current edge, your marks, at the right time. The final word is always
> **birds, bait, and marks on your sounder.** Always check official marine weather before going out.

## Files

- `tuna.py` — the engine (run this)
- `satellite.py` — satellite SST + chlorophyll fetch + cache
- `spots.json` — your home port + GPS marks
- `logbook.json` — your trip history (auto-written)
- `report.html` — the phone report (auto-written)
- `sat_cache.json` — last good satellite pull (auto-written)
