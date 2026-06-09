from tuna.spots import load_spots


def test_spots_load_and_are_nonempty():
    spots = load_spots()
    assert len(spots) >= 5


def test_spot_ids_are_unique():
    ids = [s.id for s in load_spots()]
    assert len(ids) == len(set(ids))


def test_spots_within_lebanon_bounds():
    for s in load_spots():
        assert 33.0 <= s.lat <= 34.8, f"{s.id} lat out of range"
        assert 34.8 <= s.lon <= 36.1, f"{s.id} lon out of range"


def test_spots_have_descriptions():
    for s in load_spots():
        assert s.name and s.area and s.structure
