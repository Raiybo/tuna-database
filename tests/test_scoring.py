from tuna import config, scoring


def test_sst_score_bands():
    assert scoring.sst_score(21.0) == 1.0      # optimal
    assert scoring.sst_score(25.0) == 0.6      # shoulder
    assert scoring.sst_score(27.0) == 0.3      # marginal
    assert scoring.sst_score(10.0) == config.SST_FLOOR


def test_wave_score_bands():
    assert scoring.wave_score(0.4) == 1.0      # glassy
    assert scoring.wave_score(1.2) == 0.7      # chop
    assert scoring.wave_score(1.9) == 0.4      # rough
    assert scoring.wave_score(3.0) == config.WAVE_FLOOR


def test_front_scores_uniform_water_is_baseline():
    out = scoring.front_scores([22.0, 22.1, 22.0, 21.9])
    assert all(v == config.FRONT_BASELINE for v in out)


def test_front_scores_rewards_the_edges():
    # Clear break: coldest and warmest sit on the edges, the median is bland.
    out = scoring.front_scores([18.0, 21.0, 24.0])
    assert out[0] > out[1] and out[2] > out[1]


def test_front_scores_handles_missing_values():
    out = scoring.front_scores([20.0, None, 25.0])
    assert out[1] == config.FRONT_BASELINE
    assert len(out) == 3


def test_combine_weights_sum_to_one():
    total = config.WEIGHT_SST + config.WEIGHT_WAVE + config.WEIGHT_FRONT
    assert abs(total - 1.0) < 1e-9


def test_combine_perfect_conditions():
    s = scoring.combine(1.0, 1.0, 1.0)
    assert s.total == 1.0


def test_rating_thresholds():
    assert config.rating(0.9) == "PRIME"
    assert config.rating(0.6) == "GOOD"
    assert config.rating(0.4) == "FAIR"
    assert config.rating(0.1) == "POOR"
