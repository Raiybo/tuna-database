"""Multi-day, hourly bluefin forecast: which day, and the peak bite window.

For each spot we pull hourly marine + weather over the next N days (two batched
requests), score every daylight hour with the time-of-day 'feeding' factor, then
per day pick the best reachable spot, its peak hour and the contiguous window
around it, a verdict, and the patterns that line up.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import conditions as conditions_mod
from . import config, patterns, scoring, seasonality
from .sources import openmeteo_marine, openmeteo_weather
from .sources import solunar as solunar_mod
from .spots import Home, Spot, load_catches, load_home, load_spots


def _at(seq, i):
    if seq is None or i is None or i < 0 or i >= len(seq):
        return None
    return seq[i]


@dataclass
class DayForecast:
    date: str
    weekday: str
    is_today: bool
    verdict: str
    score: float
    rating: str
    best_spot: Spot
    best_dist_nm: float
    best_heading: str
    peak_hour: str
    peak_window: str
    sst: float | None
    wind_min: float | None
    wind_max: float | None
    wind_dir: float | None
    wave_max: float | None
    pressure_trend: float | None
    patterns: list
    confidence: str
    moon: dict
    curve: list          # [(hour_int, score)] for the best spot


@dataclass
class Forecast:
    home: Home
    days: list           # chronological DayForecast


def _merge(marine, weather):
    out = []
    for m, w in zip(marine, weather):
        rec = {}
        mi = {t: k for k, t in enumerate(m["time"])}
        pres = w["pressure"]
        canonical = w["time"] or m["time"]
        for k, t in enumerate(canonical):
            j = mi.get(t)
            trend = None
            if k >= 3 and _at(pres, k) is not None and _at(pres, k - 3) is not None:
                trend = round(pres[k] - pres[k - 3], 2)
            rec[t] = {
                "sst": _at(m["sst"], j), "wave": _at(m["wave"], j),
                "current": _at(m["current"], j),
                "wind": _at(w["wind"], k), "gust": _at(w["gust"], k),
                "wind_dir": _at(w["wind_dir"], k), "pressure": _at(pres, k),
                "trend": trend, "cloud": _at(w["cloud"], k),
            }
        out.append(rec)
    return out


def _peak_window(curve):
    pi = max(range(len(curve)), key=lambda i: curve[i][1])
    peak_h, peak_s = curve[pi][0], curve[pi][1]
    lo = hi = pi
    while lo - 1 >= 0 and curve[lo - 1][1] >= peak_s - config.WINDOW_DROP:
        lo -= 1
    while hi + 1 < len(curve) and curve[hi + 1][1] >= peak_s - config.WINDOW_DROP:
        hi += 1
    return peak_h, curve[lo][0], curve[hi][0], peak_s


def _day_verdict(score, max_wind, max_wave):
    if (max_wind or 0) > config.BLOWOUT_WIND_KMH or (max_wave or 0) > config.BLOWOUT_WAVE_M:
        return "TOUGH"
    if score >= 0.70:
        return "GO"
    if score >= 0.55:
        return "DECENT"
    if score >= 0.40:
        return "MARGINAL"
    return "SLOW"


def _solunar_for(date: str, lon: float, offset: int) -> dict:
    y, mo, d = (int(x) for x in date.split("-"))
    utc_noon = datetime(y, mo, d, 12, tzinfo=timezone.utc) - timedelta(seconds=offset)
    return solunar_mod.solunar(utc_noon, lon, offset)


def _hours_for(rec, date):
    out = []
    for t, v in rec.items():
        if t[:10] != date:
            continue
        h = int(t[11:13])
        if h in config.DAYLIGHT_HOURS:
            out.append((h + int(t[14:16]) / 60.0, t, v))
    out.sort()
    return out


def build_forecast(days: int | None = None, home_override: Home | None = None) -> Forecast:
    days = days or config.FORECAST_DAYS
    spots = load_spots()
    home = home_override or load_home()
    catches = load_catches()

    conds = conditions_mod.gather(spots, home)
    chl = [c.chl_used for c in conds]
    dist_nm = [c.dist_nm for c in conds]
    heading = [c.heading for c in conds]
    in_range = [c.in_range for c in conds]

    marine = openmeteo_marine.fetch_series_multi(spots, days)
    weather = openmeteo_weather.fetch_series_multi(spots, days)
    merged = _merge(marine, weather)
    offset = next((m["offset"] for m in marine if m.get("offset")), 7200)

    canonical = (weather[0]["time"] if weather and weather[0]["time"]
                 else (marine[0]["time"] if marine else []))
    dates = sorted({t[:10] for t in canonical})
    today = (datetime.now(timezone.utc) + timedelta(seconds=offset)).strftime("%Y-%m-%d")

    out_days = []
    for date in dates:
        sol = _solunar_for(date, home.lon, offset)
        seasonal = seasonality.month_score(date)

        # representative midday SST per spot -> daily thermal-front field
        rep_sst = []
        for i in range(len(spots)):
            noon = merged[i].get(f"{date}T12:00", {})
            rep_sst.append(noon.get("sst"))
        front_day = scoring.front_scores(rep_sst)

        # per-spot daylight bite curve
        spot_curves = []     # list of (curve, hours_meta)
        for i in range(len(spots)):
            curve = []
            for hourf, t, rec in _hours_for(merged[i], date):
                factors = {
                    "sst": scoring.sst_score(rec["sst"]) if rec["sst"] is not None else None,
                    "front": front_day[i],
                    "bait": scoring.bait_score(chl[i]),
                    "current": (scoring.current_score(rec["current"])
                                if rec["current"] is not None else None),
                    "castability": scoring.castability_score(rec["wave"], rec["wind"]),
                    "pressure": scoring.pressure_score(rec["trend"]),
                    "solunar": sol["day_score"],
                    "feeding": scoring.feeding_time_score(hourf, sol),
                    "seasonal": seasonal,
                }
                sc, _ = scoring.combine_weighted(factors, config.WEIGHTS_HOURLY)
                curve.append((hourf, sc, rec))
            spot_curves.append(curve)

        # best reachable spot = highest single-hour score (prefer in range)
        def spot_peak(i):
            return max((s for _, s, _ in spot_curves[i]), default=0.0)

        candidates = [i for i in range(len(spots)) if in_range[i] and spot_curves[i]]
        if not candidates:
            candidates = [i for i in range(len(spots)) if spot_curves[i]]
        if not candidates:
            continue
        bi = max(candidates, key=spot_peak)
        curve = spot_curves[bi]

        peak_h, win_lo, win_hi, peak_s = _peak_window(curve)
        peak_rec = min(curve, key=lambda c: abs(c[0] - peak_h))[2]

        winds = [c[2]["wind"] for c in curve if c[2]["wind"] is not None]
        waves = [c[2]["wave"] for c in curve if c[2]["wave"] is not None]
        # blow-out check across all reachable spots that day
        all_wind = [c[2]["wind"] for i in candidates for c in spot_curves[i]
                    if c[2]["wind"] is not None]
        all_wave = [c[2]["wave"] for i in candidates for c in spot_curves[i]
                    if c[2]["wave"] is not None]
        verdict = _day_verdict(peak_s, max(all_wind, default=0), max(all_wave, default=0))

        noon = merged[bi].get(f"{date}T12:00", {})
        ctx = {
            "front_spread": (max([s for s in rep_sst if s is not None], default=0)
                             - min([s for s in rep_sst if s is not None], default=0)
                             if any(s is not None for s in rep_sst) else None),
            "pressure_trend": peak_rec.get("trend"),
            "solunar": sol,
            "chl": chl[bi],
            "wind_peak": peak_rec.get("wind"),
            "wave_peak": peak_rec.get("wave"),
            "sst": noon.get("sst"),
            "peak_hour": int(peak_h),
            "moon_phase": sol["phase"],
        }
        pats, confidence = patterns.detect(ctx, catches)

        out_days.append(DayForecast(
            date=date,
            weekday=datetime(*[int(x) for x in date.split("-")]).strftime("%a"),
            is_today=(date == today),
            verdict=verdict,
            score=round(peak_s, 3),
            rating=config.rating(peak_s),
            best_spot=spots[bi],
            best_dist_nm=round(dist_nm[bi], 1),
            best_heading=heading[bi],
            peak_hour=f"{int(peak_h):02d}:00",
            peak_window=f"{int(win_lo):02d}:00-{int(win_hi) + 1:02d}:00",
            sst=round(noon["sst"], 1) if noon.get("sst") is not None else None,
            wind_min=round(min(winds), 0) if winds else None,
            wind_max=round(max(winds), 0) if winds else None,
            wind_dir=peak_rec.get("wind_dir"),
            wave_max=round(max(waves), 1) if waves else None,
            pressure_trend=peak_rec.get("trend"),
            patterns=pats,
            confidence=confidence,
            moon=sol,
            curve=[(int(h), round(s, 3)) for h, s, _ in curve],
        ))

    return Forecast(home=home, days=out_days)


def best_day(fc: Forecast):
    """The highest-scoring upcoming day."""
    return max(fc.days, key=lambda d: d.score) if fc.days else None
