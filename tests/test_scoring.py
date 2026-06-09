from tuna import config, scoring


def test_sst_score_bands():
    assert scoring.sst_score(21.0) == 1.0
    assert scoring.sst_score(25.0) == 0.6
    assert scoring.sst_score(27.0) == 0.3
    assert scoring.sst_score(10.0) == config.SST_FLOOR


def test_wave_and_wind_scores():
    assert scoring.wave_score(0.4) == 1.0
    assert scoring.wave_score(3.0) == config.WAVE_FLOOR
    assert scoring.wind_score(5) == 1.0
    assert scoring.wind_score(50) == config.WIND_FLOOR


def test_current_score():
    assert scoring.current_score(1.0) == 1.0      # nice feeding drift
    assert scoring.current_score(0.1) == 0.45     # slack
    assert scoring.current_score(12) == config.CURRENT_FLOOR


def test_pressure_score_none_and_bands():
    assert scoring.pressure_score(None) is None
    assert scoring.pressure_score(-1.0) == 1.0    # slowly falling = prime
    assert scoring.pressure_score(5.0) == 0.45    # rising fast


def test_bait_score():
    assert scoring.bait_score(None) is None
    assert scoring.bait_score(0.3) == 1.0
    assert scoring.bait_score(0.01) == 0.3
    assert scoring.bait_score(2.0) == config.CHL_FLOOR


def test_castability_blends_and_degrades():
    both = scoring.castability_score(0.4, 5)
    assert both == 1.0
    assert scoring.castability_score(None, 5) == scoring.wind_score(5)
    assert scoring.castability_score(0.4, None) == scoring.wave_score(0.4)
    assert scoring.castability_score(None, None) is None


def test_front_scores():
    assert all(v == config.FRONT_BASELINE
               for v in scoring.front_scores([22.0, 22.1, 22.0]))
    edged = scoring.front_scores([18.0, 21.0, 24.0])
    assert edged[0] > edged[1] and edged[2] > edged[1]


def test_weights_sum_to_one():
    assert abs(sum(config.WEIGHTS.values()) - 1.0) < 1e-9


def test_combine_weighted_renormalises_over_present_factors():
    # Only one factor present -> its own score.
    total, contrib = scoring.combine_weighted({"sst": 1.0, "front": None})
    assert total == 1.0 and "front" not in contrib
    # Two present factors -> weighted average over just those two.
    total2, _ = scoring.combine_weighted({"sst": 1.0, "castability": 0.0})
    expect = config.WEIGHTS["sst"] / (config.WEIGHTS["sst"] + config.WEIGHTS["castability"])
    assert abs(total2 - round(expect, 4)) < 1e-3


def test_haversine_and_sighting_boost():
    from datetime import datetime, timezone
    assert scoring.haversine_km(33.9, 35.5, 33.9, 35.5) == 0.0
    now = datetime(2026, 6, 9, 12, tzinfo=timezone.utc)
    near = [{"lat": 33.9, "lon": 35.5, "_dt": datetime(2026, 6, 9, 0, tzinfo=timezone.utc)}]
    far = [{"lat": 30.0, "lon": 30.0, "_dt": datetime(2026, 6, 9, 0, tzinfo=timezone.utc)}]
    assert scoring.sighting_boost(33.9, 35.5, near, now) > 0
    assert scoring.sighting_boost(33.9, 35.5, far, now) == 0.0
