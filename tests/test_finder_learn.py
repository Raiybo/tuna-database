from tuna import config, finder, learn, seasonality


def test_seasonality_summer_peaks():
    assert seasonality.month_score(7) == 1.0
    assert seasonality.month_score(1) < seasonality.month_score(6)
    assert seasonality.month_score("2026-08-15") == 1.0
    assert seasonality.label(1.0) == "peak season"
    assert seasonality.label(0.3) == "off season"


def test_weights_include_seasonal_and_sum_to_one():
    assert "seasonal" in config.WEIGHTS
    assert abs(sum(config.WEIGHTS.values()) - 1.0) < 1e-9
    assert abs(sum(config.WEIGHTS_HOURLY.values()) - 1.0) < 1e-9
    assert abs(sum(config.FINDER_WEIGHTS.values()) - 1.0) < 1e-9


def test_finder_field_gradient_and_clamp():
    assert finder._clamp(2.0) == 1.0 and finder._clamp(-1.0) == 0.0
    # a sharp step between two clusters -> non-zero gradient at the seam
    pts = [{"lat": 33.90, "lon": 35.40, "val": 24.0},
           {"lat": 33.91, "lon": 35.40, "val": 24.1},
           {"lat": 33.92, "lon": 35.40, "val": 25.5}]
    f = finder._Field(pts)
    assert f.gradient(33.91, 35.40, 5.0) > 0
    assert f.nearest(33.90, 35.40, 1.0)["val"] == 24.0


def test_learn_summary_empty_and_record():
    rec = learn.new_record("catch", n=2, spot_id="beirut-canyon", hour=6, sst_c=24.8)
    assert rec["result"] == "catch" and rec["n"] == 2 and rec["spot_id"] == "beirut-canyon"
    assert "date" in rec
    # shipped catches.json holds only an example row -> summary prompts to log
    text = learn.summary()
    assert "log" in text.lower()
