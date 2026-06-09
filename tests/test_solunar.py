from datetime import datetime, timezone

from tuna.sources import solunar


def test_solunar_shape_and_ranges():
    now = datetime(2026, 6, 9, 10, tzinfo=timezone.utc)
    s = solunar.solunar(now, 35.59, 3 * 3600)
    assert 0 <= s["illumination_pct"] <= 100
    assert 0.55 <= s["day_score"] <= 1.0
    assert len(s["major_periods"]) == 2 and len(s["minor_periods"]) == 2
    for t in s["major_periods"] + s["minor_periods"]:
        hh, mm = t.split(":")
        assert 0 <= int(hh) < 24 and 0 <= int(mm) < 60


def test_new_moon_scores_high():
    # Reference new moon epoch -> day score near the max.
    new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    s = solunar.solunar(new, 35.59, 3 * 3600)
    assert s["day_score"] > 0.95
    assert "Moon" in s["phase"]
