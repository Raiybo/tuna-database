"""Unit tests for the forecast/pattern pure logic (no network)."""
from tuna import config, patterns, scoring


def test_feeding_time_peaks_in_light_window():
    sol = {"major_periods": ["12:00", "00:00"], "minor_periods": ["06:00", "18:00"]}
    dawn = scoring.feeding_time_score(6.0, sol)      # inside 05-08 window + minor
    midday = scoring.feeding_time_score(13.0, sol)   # outside light, near a major
    deadtime = scoring.feeding_time_score(15.0, sol)  # away from everything
    assert dawn == 1.0
    assert deadtime < dawn
    assert deadtime <= midday


def test_feeding_solunar_major_stacks_to_peak():
    # A major landing right on the dawn window -> stacked peak (1.0).
    sol = {"major_periods": ["06:00"], "minor_periods": []}
    assert scoring.feeding_time_score(6.0, sol) == 1.0


def test_combine_weighted_accepts_custom_weights():
    factors = {"sst": 1.0, "feeding": 0.0}
    total, contrib = scoring.combine_weighted(factors, config.WEIGHTS_HOURLY)
    w = config.WEIGHTS_HOURLY
    expect = w["sst"] / (w["sst"] + w["feeding"])
    assert abs(total - round(expect, 4)) < 1e-3
    assert set(contrib) == {"sst", "feeding"}


def test_patterns_detect_strong_setup():
    ctx = {
        "front_spread": 0.9,            # strong thermal break
        "pressure_trend": -1.0,         # pre-frontal feed
        "solunar": {"major_periods": ["06:00"], "minor_periods": [],
                    "day_score": 0.95, "phase": "Full Moon", "illumination_pct": 100},
        "chl": 0.3,                     # productive water
        "wind_peak": 8, "wave_peak": 0.5,  # calm casting
        "sst": 24.0, "peak_hour": 6, "moon_phase": "Full Moon",
    }
    pats, confidence = patterns.detect(ctx, catches=[])
    names = {p.name for p in pats}
    assert "Thermal break active" in names
    assert "Pre-frontal feed" in names
    assert "Solunar stack at light" in names
    assert confidence == "High"


def test_patterns_quiet_when_flat():
    ctx = {"front_spread": 0.1, "pressure_trend": 0.0,
           "solunar": {"major_periods": ["13:00"], "minor_periods": [],
                       "day_score": 0.6, "phase": "First Quarter"},
           "chl": None, "wind_peak": 25, "wave_peak": 1.5,
           "sst": 24.0, "peak_hour": 13, "moon_phase": "First Quarter"}
    pats, confidence = patterns.detect(ctx, catches=[])
    assert confidence == "Low"


def test_catch_learning_matches_logged_conditions():
    ctx = {"front_spread": 0.2, "pressure_trend": -0.8, "solunar": {"day_score": 0.6},
           "chl": None, "wind_peak": 10, "wave_peak": 0.6,
           "sst": 25.0, "peak_hour": 6, "moon_phase": "Last Quarter"}
    catches = [{"result": "catch", "n": 1, "sst_c": 25.2, "wind_kmh": 12,
                "pressure_trend": -0.5, "moon": "Last Quarter", "hour": 6}]
    pats, _ = patterns.detect(ctx, catches)
    assert any("past catches" in p.name for p in pats)
