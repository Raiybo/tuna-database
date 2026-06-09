from tuna.spots import load_home, load_sightings, load_spots


def test_spots_load_and_are_nonempty():
    assert len(load_spots()) >= 5


def test_spot_ids_are_unique():
    ids = [s.id for s in load_spots()]
    assert len(ids) == len(set(ids))


def test_spots_within_lebanon_bounds():
    for s in load_spots():
        assert 33.0 <= s.lat <= 34.8, f"{s.id} lat out of range"
        assert 34.8 <= s.lon <= 36.1, f"{s.id} lon out of range"


def test_home_loads_with_range():
    h = load_home()
    assert 33.0 <= h.lat <= 34.8 and 34.8 <= h.lon <= 36.1
    assert h.max_range_km > 0


def test_sightings_skip_examples():
    # The shipped sightings file contains only an example row -> ignored.
    for s in load_sightings():
        assert not s.get("example")
        assert "_dt" in s
